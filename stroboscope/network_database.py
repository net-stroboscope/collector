"""
Defines the Network Database used by the collector.

Typically, the graph (NetGraph) should be manipulated to contain the complete
network topology.
"""
import logging
import networkx as nx
from ipaddress import ip_interface

from .algorithms.graph import get_spt


LOG = logging.getLogger(__name__)
ARROW = '->'


class NetDB(object):
    """Hold the complete topology, as well as past measurements."""

    def __init__(self, max_bw=50, past_campaigns_considered=10):
        """
        Initialize the NetDB.

        :max_bw: Maximal admissible bandwidth for a flow
        :past_campaigns_considered: How long should we keep bandwidth
                                    statistics for a given flow (number of
                                    measurent campaigns)
        """
        self.graph = NetGraph()
        self.max_bw = max_bw
        self.router_addresses = {}
        self.past_measurements = {}
        self.past_campaigns_considered = past_campaigns_considered
        self.has_no_forwarding_anomalies = True  # Should be updated at runtime
        # by post-processing script analyzing MIRROR queries output

    def resolve_region(self, region):
        """
        Return a well-defined region.

        If the region was already well-defined, return None, otherwise return
        the list of path forming the region
        """
        if not region:
            return region
        walker = iter(region)
        # Replace a starting arrow
        head = region[0]
        if head == ARROW:
            paths = [[e] for e in self.graph.egresses]
        else:
            paths = [[head]]
            next(walker)  # consume the walker as we added its entry
        for hop in walker:
            if hop != ARROW:
                # Add the new hop
                for p in paths:
                    p.append(hop)
                # advance
                continue
            # Otherwise handle the arrow
            try:
                # Advance until the next hop
                while hop == ARROW:
                    hop = next(walker)
                terminals = [hop]
            except StopIteration:  # the arrow is the last entry
                terminals = list(self.graph.egresses)
            # Concat all paths with the SPT from their last hop to
            # all terminals
            new = []
            for p in paths:
                # Track all concatenations
                extensions = []
                for terminal in terminals:
                    # which are all spt per terminal minus the hop itself
                    extensions.extend(subp[1:] for subp in
                                      self.graph.spt[p[-1]][terminal])
                ext_iter = iter(extensions)
                # extend the first path
                first_concat = (next(ext_iter))
                for concat in ext_iter:
                    # create new instance afterwards
                    new.append(p[:] + concat)
                p.extend(first_concat)
            paths.extend(new)
        return paths

    def usage_prediction(self, prefix, campaign_number=0):
        """Return the predicted bandwidth for prefix."""
        value = self.max_bw
        try:
            value = max(bw for idx, bw in self.past_measurements[prefix])
        except KeyError:
            # Fallback to netflow data with proprietary channel
            try:
                value = self.netflow_estimation(prefix)
            except NoNetFlowRecords:
                pass
        if value > self.max_bw:
            LOG.warning('%s estimated demand is greater than the maximal bw'
                        ' (%s > %s)', prefix, value, self.max_bw)
            value = self.max_bw
        return value

    def netflow_estimation(self, prefix):
        """Return the traffic demand seen by netflow for this prefix."""
        # Integrate with existing NetFlow tooling if you have it
        raise NoNetFlowRecords

    def has_interfering_traffic(self, prefix, region):
        """
        Check whether there are flows for the prefix interfering.

        Interfering flows are flows for a prefix not starting in the region,
        then going through a node adjacent to the region but not in it, then
        moving away from the region. This requires information from IGP feeds
        and/or BGP to solve.
        """
        return False

    def record_bandwidth_usage(self, prefix, rate, campaign_number=0):
        """Register the used bandwidth from a prefix."""
        try:
            prior = [(idx, bw) for idx, bw in self.past_measurements[prefix]
                     if idx + self.past_campaigns_considered < campaign_number]
        except KeyError:
            prior = [(campaign_number, rate)]
        self.past_measurements[prefix] = prior

    def update_router_addresses(self):
        """Update the cached mapping of addresses->router id."""
        for u, _, attr in self.graph.edges_iter(data=True):
            self.router_addresses[
                attr[self.graph.ADDRESS_KEY].ip.compressed] = u

    def interface_name(self, u, v):
        """Return the interface name on router u facing v."""
        return self.graph.if_name(u, v)

    def max_router_to_collector_delay(self):
        """Return the maximal delay from a router to the collector."""
        # Link with processing application if present
        return 25

    def max_path_delay(self):
        """Return the maximal delay over a path in the network."""
        # Link with processing application if present
        return 50

    def router_adddress(self, r):
        """Return an IP address of a router on which we can connect."""
        return self.graph.router_address(r)

    def has_edge(self, u, v):
        return self.graph.has_edge(u, v)


class NetGraph(nx.DiGraph):
    """A network graph."""
    # edge property names
    METRIC_KEY = 'cost'
    IFNAME_KEY = 'if_name'
    ADDRESS_KEY = 'address'

    def __init__(self, *a, **kw):
        self.edge_spt = self.spt = self.edge_spt_cost = self.spt_cost = {}
        self.egresses = set()
        super(NetGraph, self).__init__(*a, **kw)

    def register_egress(self, n, **kw):
        """Register border router."""
        self.egresses.add(n)
        self.register_router(n, egress=True, **kw)

    def register_router(self, n, **kw):
        """Register router."""
        self.add_node(n, router=True, **kw)

    def register_link(self, u, v, uv_prop=None, vu_prop=None, **common):
        """
        Register a link between two nodes and interface properties.

        :u, v: the routers delilmiting the link
        :uv_prop: the properties of the interface on u facing v
        :common: properties global to both link

        See the class variables *_KEY for names
        """
        self.register_unidirectional_link(u, v, uv_prop, common)
        self.register_unidirectional_link(v, u, vu_prop, common)

    def register_unidirectional_link(self, u, v, attr, defaults):
        """See register_link."""
        if attr is None:
            attr = {}
        attr.update(defaults)
        attr.setdefault(self.METRIC_KEY, 1)
        attr.setdefault(self.IFNAME_KEY, 'unknown')
        attr.setdefault(self.ADDRESS_KEY, ip_interface(u'0.0.0.0/0'))
        attr[self.METRIC_KEY] = float(attr[self.METRIC_KEY])
        attr[self.ADDRESS_KEY] = ip_interface(attr[self.ADDRESS_KEY])
        self.add_edge(u, v, attr_dict=attr)

    def build_spt(self):
        """Build the shortest-path tree for the current graph."""
        self.spt, self.spt_cost = get_spt(self, self.METRIC_KEY)
        # If we provide no cost key, we force the spt to be in term of edge#
        self.edge_spt, self.edge_spt_cost = get_spt(self, None)
        return self.spt

    def if_name(self, u, v):
        """The name of the interface on u facing v."""
        return self[u][v][self.IFNAME_KEY]

    def if_address(self, u, v, attr=None):
        """"The address of the interface on u facing v."""
        return (self[u][v][self.ADDRESS_KEY] if attr is None
                else attr[self.ADDRESS_KEY])

    def router_address(self, r):
        """Return a random IP address for the router."""
        return ip_interface(
            self.if_address(r,
                            next(self.edges_iter(nbunch=[r], data=True))[1])
        ).ip.compressed


class NoNetFlowRecords(ValueError):
    """NetFlow cannot be used to estimate the demand of a prefix."""
