"""The Collector class is the central orchestrator or the framework."""
import logging
import time

import radix

import stroboscope as core
from .network_database import NetDB
from .measurement_processor import MeasurementProcessor
from .rule_backend import LinuxBackend
from .dissect import Dissector
from .requirements import Requirements, Confine
from .algorithms.schedule import NoSchedule

LOG = logging.getLogger(__name__)


class Collector(object):
    """This class compiles requirements and executes measurement campaigns."""

    def __init__(self, measurement_processor=MeasurementProcessor(),
                 rule_backend=LinuxBackend, listen_on=u'0.0.0.0',
                 ssh_keypath=None, ssh_username='root',
                 encap_dst='10.0.0.1', phys_dst=None):
        """
        Initialize the collector and its applications.

        :measurement_processor: A class or object that will process the
                                measurement result stream
        :rule_backend: The provider of a deactivate function/method that can be
                       used to activate mirroring rules
        :listen_on: The IP address to listen on
        :ssh_keypath: The path to the ssh key to be used to log into routers
        :ssh_username: The username for SSH connections
        :encap_dst: The GRE tunnel end for the mirrored packets
        :phys_dst: The IP address of the collector
        """
        # Make sure to actually edit the graph at some point and
        # call update_router_addresses() otherwise queries won't be resolved
        rule_backend.register_connection_properties(
            ssh_filename=ssh_keypath, username=ssh_username)
        core.RULE_BACKEND = rule_backend
        core.RULE_BACKEND.ENCAP_ADDRESS = encap_dst
        core.RULE_BACKEND.COLLECTOR_ADDRESS = phys_dst
        self.net = NetDB()
        self.consumer = measurement_processor
        self.dissector = Dissector(self.net.router_addresses, listen_on,
                                   self.process_packet)
        self.requirements = Requirements(queries=[])
        self.past_schedule_prop = None
        self.current_campaign = 0
        self.bw_usage = {}  # bw left per query
        self.activation_list = {}  # router->radix(prefix->rule)
        self.traffic_slices = {}  # location -> [pkts]
        super(Collector, self).__init__()

    def load_requirements(self, filename):
        """Load requirements from a file."""
        try:
            with open(filename, 'r') as f:
                req_text = f.read()
        except IOError as e:
            LOG.error("Cannot load the requirements from file %s: %s",
                      filename, e)
        else:
            self.parse_requirements(req_text)

    def parse_requirements(self, text):
        """Load the new monitoring requirements."""
        self.requirements = Requirements.from_text(text)
        if not self.requirements:
            LOG.warning('Could not parse the requirements!')
            return
        self.requirements.min_slot_duration =\
            core.RULE_BACKEND.MIN_SLOT_DURATION
        self.execute_campaigns()

    def execute_campaigns(self):
        next_id = 0
        while core.RUNNING:
            self.current_campaign = next_id
            self.traffic_slices = {}
            self.consumer.start()
            try:
                next_id = self.start_measurements(next_id)
            except NoSchedule as e:
                LOG.error('Could not compute the measurment campaign!')
                LOG.error('%s', e)
                LOG.error('Aborting')
                break
            time.sleep(self.requirements.every)
        self.stop()

    def start_measurements(self, campaign_id=0):
        """Start the measurement campaigns"""
        schedule_prop = self.requirements.compile(self.net, campaign_id)
        if schedule_prop is None:
            schedule_prop = self.past_schedule_prop
        else:
            self.past_schedule_prop = schedule_prop
        schedule, locations, queries = schedule_prop
        # timeslot constants
        slot_len = self.requirements.slot_duration / 1000
        delay_len = self.requirements.inter_slot_delay / 1000
        # slot count per query
        slot_count = {q: 0 for q in queries}
        # Count how many times each query got actually activated
        activation_count = {q: 0 for q in queries}
        for slot in schedule:
            for q in slot:
                slot_count[q] += 1
        # allowed bw per query
        self.bw_usage = {q: (0 if isinstance(q, Confine) else
                             q.cost * slot_len * slot_count[q])
                         for q in queries}
        for slot in schedule:
            self.execute_slot(slot, locations, activation_count)
            time.sleep(slot_len + delay_len)
        # record the traffic statistics per prefix to update the estimations
        prefix_demands = {}
        for q in queries:
            orig_budget = q.cost * slot_len * slot_count[q]
            consumed_budget = orig_budget - self.bw_usage[q]
            seen = prefix_demands.get(q.prefix, 0)
            prefix_demands[q.prefix] = max(
                seen, consumed_budget / activation_count[q] / slot_len)
        for p, demand in prefix_demands.iteritems():
            self.net.record_bandwidth_usage(p, demand, campaign_id)
        # send the traffic slices for analyzis
        self.consumer.process(locations, queries, self.traffic_slices)
        return campaign_id + 1

    def execute_slot(self, slot, locations, activation_count):
        """Execute a given slot."""
        self.activation_list = {}
        for q in slot:
            if q.is_disabled:
                continue  # Query exhausted its budget
            activation_count[q] += 1
            for rule in locations[q]:
                location = rule.location
                if rule.interface:
                    # resolve interface name if present
                    rule.interface = self.net.interface_name(*rule.interface)
                try:
                    rtree = self.activation_list[location]
                except KeyError:
                    rtree = self.activation_list[location] = radix.Radix()
                rnode = rtree.add(rule.prefix.compressed)
                rnode.data['rule'] = rule
        for location, rule_tree in self.activation_list.iteritems():
            core.RULE_BACKEND.activate(
                self.net.router_adddress(location),
                [r.data['rule'] for r in rule_tree],
                duration=self.requirements.slot_duration)

    def process_packet(self, pkt):
        """The dissector has received a mirrored packet."""
        try:
            rtree = self.activation_list[pkt.router]
            rnode = rtree.search_best(pkt.dst.compressed)
            if rnode is None:
                raise KeyError
            rule = rnode.data['rule']
        except KeyError:
            LOG.warning('Received mirrored packet from router without '
                        'corresponding mirroring rule ?')
            return
        # append to the proper slice
        try:
            self.traffic_slices[rule.location].append(pkt)
        except KeyError:
            self.traffic_slices[rule.location] = [pkt]
        # update traffic consumptions
        for query in rule.query:
            if not rule.EXPECT_TRAFFIC:
                LOG.warning('%s received unexpected traffic!', query)
                query.is_disabled = True
            left = self.bw_usage[query] - len(pkt)
            # We will not be able to activate it again
            if left < query.cost * self.requirements.slot_duration:
                query.is_disabled = True
            self.bw_usage[query] = left

    def stop(self):
        self.consumer.stop()

    def join(self):
        pass
