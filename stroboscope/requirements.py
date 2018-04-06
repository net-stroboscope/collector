"""Define the requirement language of stroboscope."""
import itertools
import logging
import functools
from pkg_resources import resource_string

import tatsu
from tatsu.exceptions import TatSuException
from ipaddress import ip_network

from .algorithms.key_points import find_key_points
from .algorithms.confine import CONFINE_OPT
from .algorithms.schedule import balance_and_schedule


LOG = logging.getLogger(__name__)

PARSER_MODEL = tatsu.compile(resource_string(__name__, 'grammar.tatsu'))


class Requirements(object):
    """Requirements instruct a collector of the measurement to perform."""

    def __init__(self, queries, using=10, during=.5, every=5):
        """
        Configure the requirements for the measurement campaign.

        :queries: a list of queries defining the measurements
        :using: the bandwidth budget (in Mbps)
        :during: the time budget (in s)
        :every: the spacing between successive measurement campaigns (in s)
        """
        self.queries = queries
        self.using = float(using)
        self.during = float(during)
        self.every = float(every)
        self.slot_count = 0
        self.slot_duration = 0
        self.min_slot_duration = 25  # Minimal timeslot duration (ms)
        self.inter_slot_delay = 0

    @classmethod
    def from_text(cls, text):
        """Parse text to create Requirements."""
        try:
            ast = PARSER_MODEL.parse(text)
            return _make_requirements_from_ast(ast, cls)
        except (ValueError, TatSuException) as e:
            LOG.error('Could not parse requirements: %s', e)
            return None

    def compile(self, net, campaign_id):
        """
        Compile the requirements to produce a mirroring schedule.

        :net: the network information
        :campaign_id: the measurement campaign id
        :return: (schedule, mirroring locations, well-defined queries) or
                 None if unchanged
        """
        defined_queries = self.what(net)
        if not defined_queries:  # no changes, signal it
            return None
        mirroring_locations = self.where(net, defined_queries)
        schedule = self.when(defined_queries)
        return schedule, mirroring_locations, defined_queries

    def what(self, net):
        """Resolve loosely defined queries."""
        changes_detected = False
        defined_queries = []
        slot_count = self.slot_count
        self.derive_slot_count(net)
        if slot_count != self.slot_count:
            changes_detected = True
        for query in self.queries:
            query.is_disabled = False
            # Update demand prediction
            old_prediction = query.prediction
            new_prediction = net.usage_prediction(query.prefix)
            if old_prediction != new_prediction:
                query.prediction = new_prediction
                changes_detected = True
            # Update monitored regions
            old_region = query.subregions
            new_region = net.resolve_region(query.region)
            if old_region != new_region:
                changes_detected = True
                query.subregions = new_region
            # Either add the resolved queries
            if new_region:
                defined_queries.extend(query.resolve(new_region))
            else:
                # or the base one if already well-specified
                defined_queries.append(query)
        if changes_detected:
            LOG.info('Queries resolved differently, rescheduling.')
            return defined_queries
        return None

    def derive_slot_count(self, net):
        """Compute the slot durations as well as their count."""
        max_delay = net.max_path_delay()
        self.slot_duration = max(max_delay, self.min_slot_duration)
        self.inter_slot_delay = net.max_router_to_collector_delay()
        self.slot_count = self.during * 1000 // (
            self.slot_duration + self.inter_slot_delay)

    @staticmethod
    def where(net, defined_queries):
        """Define the mirroring locations for the queries."""
        return {q: q.compile(net) for q in defined_queries}

    def budget(self):
        """Return the budget-related properties of these requirements."""
        return Budget(using=self.using, during=self.during, every=self.every,
                      maxslots=self.slot_count)

    def when(self, queries):
        """Build the measurement campaign schedule."""
        return balance_and_schedule(queries, self.budget())

    def __repr__(self):
        """Print out the requirements using our language."""
        return '%s\n%s\n' % ('\n'.join(str(q) for q in self.queries),
                             self.budget())
    __str__ = __repr__


class Budget(object):
    """The monitoring budget."""

    def __init__(self, using=5, during=5, every=5, maxslots=None, mip_gap=.05,
                 max_ilp_run=120, sigma=10):
        # Derived from the requirements
        self.using = using
        self.during = during
        self.every = every
        # Used throughout the compilation
        self.mip_gap = mip_gap  # ILP optimatility gap
        self.max_slots = maxslots  # Maximum number of slots
        self.max_ilp_run = max_ilp_run
        self.sigma = sigma

    def __eq__(self, other):
        try:
            return (self.using == other.using and
                    self.during == other.during and
                    self.every == other.every and
                    self.max_slots == other.max_slots)
        except AttributeError:
            raise NotImplementedError

    def __neq__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return 'USING %f M DURING %f s EVERY %f s # max_slots: %d' % (
            self.using, self.during, self.every, self.max_slots)


class _Query(object):
    """Base for queries."""

    COUNT = 0

    def __init__(self, prefix, on, prediction=0,
                 weight=1, name=None):
        """Build a new query for a given prefix on a given path/region."""
        self.prefix = ip_network(prefix)
        self.region = on  # The input region from the requirements
        self.subregions = on  # The resolved region
        self.locations = on  # The selected mirroring locations
        self.is_disabled = False
        self.prediction = prediction
        self.weight = weight
        _Query.COUNT += 1
        self.name = name if name is not None else 'Q%d' % _Query.COUNT

    @property
    def cost(self):
        """Return the bandwidth cost of activating this rule."""
        return len(self.locations) * self.prediction

    @classmethod
    def new(cls, prefixes, on, *a, **kw):
        """Build a list of queries from prefixes and regions."""
        return [cls(p, region, *a, **kw)
                for p in prefixes for region in on]

    def compute_locations(self, graph):
        """
        Return a list of mirroring locations for this query.

        :graph: the complete network topology
        """
        raise NotImplementedError

    def generate_rules(self):
        """Return the mirroring rules for this query current locations."""
        raise NotImplementedError

    def resolve(self, regions):
        """Return well defined queries for the following regions."""
        raise NotImplementedError

    def compile(self, net):
        """Compile this query and return the mirroring rules."""
        self.locations = self.compute_locations(net)
        return self.generate_rules()

    @classmethod
    def query_type(cls):
        """Return the type of this query."""
        return cls.__name__.upper()

    def __repr__(self):
        """Display the query description."""
        return '(name:%s, weight:%f) %s %s ON %s' % (
            self.name, self.weight,
            self.query_type(), self.prefix, '[%s]' % ' '.join(
                str(hop) for hop in self.region))
    __str__ = __repr__


class Mirror(_Query):
    """A MIRROR query."""

    def compute_locations(self, net):
        """Use the KPS algorithm to reduce the number of mirroring rules."""
        # Always use the most optimal algo
        return find_key_points(net.graph, self.region)

    def generate_rules(self):
        """Use MirrorRules."""
        return [MirroringRule(self, loc) for loc, _ in self.locations]

    def resolve(self, regions):
        """Return one query per region."""
        return self.new([self.prefix], regions,
                        prediction=self.prediction)

    def path_endpoints(self):
        """Return the end points of the mirrored path."""
        return self.subregions[0], self.subregions[-1]


class Confine(_Query):
    """A CONFINE query."""

    def compute_locations(self, net):
        """Use the surrounding algorithm to place the rules.."""
        # select the proper surrounding algorithm
        opt_level = 0
        if not net.has_interfering_traffic(self.prefix, self.region):
            opt_level += 1
            if net.has_no_forwarding_anomalies:
                opt_level += 1
        return CONFINE_OPT[opt_level](net.graph, self.region)

    def generate_rules(self):
        """Use ConfineRules."""
        return [ConfineRule(self, loc) for loc in self.locations]

    def resolve(self, regions):
        """Return a single query for all regions."""
        # Collapse all regions nodes
        LOG.info(regions)
        return [self.__class__(
            self.prefix, list(set(itertools.chain.from_iterable(regions))),
            prediction=self.prediction)]

    @property
    def cost(self):
        return 0


@functools.total_ordering
class MirroringRule(object):
    """A location in the network that should mirror traffic when enabled."""

    # Whether this type of mirroring rule expects traffic or not
    EXPECT_TRAFFIC = True

    def __init__(self, query, location):
        """Register the rule properties."""
        self.query = [query]
        if isinstance(location, tuple):
            self.interface = location
            self.location = location[0]
        else:
            self.interface = ''
            self.location = location

    @property
    def prefix(self):
        """Use the query's prefix."""
        return self.query[0].prefix

    def merge(self, other_rule):
        """Merge these mirroring rules."""
        self.query.extend(other_rule.query)

    def __eq__(self, other):
        """Compare based on location and prefix."""
        try:
            return self.tuple == other.tuple
        except AttributeError:
            return False

    def __lt__(self, other):
        """Define a tie breaker."""
        try:
            return self.location < other.location or self.prefix < other.prefix
        except AttributeError:
            raise NotImplementedError

    @property
    def tuple(self):
        """Return the identifying information for this rule."""
        return (self.__class__.__name__, self.prefix, self.location)

    def __repr__(self):
        """Represent the type of rules, locations and prefix."""
        return '<%s for %s at %s>' % self.tuple
    __str__ = __repr__

    def __hash__(self):
        """Hash rules based on their tuple."""
        return hash(self.tuple)


class ConfineRule(MirroringRule):
    """A CONFINE mirroring rule should never receive traffic."""

    EXPECT_TRAFFIC = False


# Parsing-related routines


def _make_requirements_from_ast(ast, req):
    budget = _parse_budget(ast)
    queries = _parse_queries(ast)
    return req(queries=queries, **budget)


class CannotParse(ValueError):
    """Cannot parse a target node."""


def _parse_error(msg, node, *a, **kw):
    pinfo = node.parseinfo
    LOG.error(*a, **kw)
    LOG.error('When parsing lines %d-%d:', pinfo.line, pinfo.endline)
    for l in pinfo.buffer.text[pinfo.pos:pinfo.endpos].split('\n'):
        LOG.error(l)
    raise CannotParse(msg)


def _parse_warning(node, *a, **kw):
    pinfo = node.parseinfo
    LOG.warning(*a, **kw)
    LOG.warning('When parsing lines %d-%d:', pinfo.line, pinfo.endline)
    for l in pinfo.buffer.text[pinfo.pos:pinfo.endpos].split('\n'):
        LOG.warning(l)


def _parse_budget(ast):
    budget = {}
    for node in ast.budget:
        if node.key == 'USING':
            budget['using'] = _bandwidth_node(node.val)
        elif node.key == 'DURING':
            budget['during'] = _duration_node(node.val)
        elif node.key == 'EVERY':
            budget['every'] = _duration_node(node.val)
        else:
            _parse_warning(node, "Unknown budget attribute %s", node.key)
    return budget


def _float_node(node):
    try:
        return float(node.amount)
    except (ValueError, TypeError):
        _parse_error('Not a number', node, "Cannot parse %s as a number",
                     node.amount)


BW_UNITS = {None: 1}
for u, coef in (('', .000001), ('k', .001), ('m', 1), ('g', 1000)):
    for c in (u.lower(), u.upper()):
        BW_UNITS[c] = BW_UNITS[c + 'b'] = BW_UNITS[c + 'bps'] = coef


def _bandwidth_node(node):
    amount = _float_node(node)
    try:
        return amount * BW_UNITS[node.unit]
    except KeyError:
        _parse_warning(node, 'Ignoring unknown bandwidth unit %s', node.unit)


TIME_UNITS = {None: 1, 's': 1, 'sec': 1, 'm': 60, 'min': 60, 'h': 3600,
              'hour': 3600, 'd': 24 * 3600, 'day': 24 * 3600, 'ms': .001,
              'millisecond': .001}


def _duration_node(node):
    amount = _float_node(node)
    try:
        return amount * TIME_UNITS[node.unit]
    except KeyError:
        _parse_warning(node, 'Ignoring unknown time unit %s', node.unit)


def _parse_queries(ast):
    queries = []
    for q in ast.queries:
        cls = None
        if q.action == 'CONFINE':
            cls = Confine
        elif q.action == 'MIRROR':
            cls = Mirror
        else:
            _parse_warning(q, 'Unknown query type %s', q.action)
        if cls is not None:
            queries.extend(cls.new(_parse_prefix_list(q), list(q.regions),
                                   **_parse_query_properties(q)))
    return queries


def _parse_prefix_list(node):
    try:
        return [ip_network(unicode(p)) for p in node.prefixes]
    except ValueError as e:
        _parse_error('Invalid prefix', node, "Cannot parse prefix: %s", e)


def _parse_query_properties(node):
    properties = {}
    if node.properties is None:
        return properties
    for prop in node.properties:
        key = prop.key
        if key == 'name':
            properties['name'] = prop.val
        elif key == 'weight':
            try:
                properties['weight'] = float(prop.val)
            except (ValueError, TypeError):
                _parse_error('Not a number', prop,
                             "Cannot parse %s as a weight", prop.val)
        else:
            _parse_warning(prop, "Unknown query properties %s", key)
    return properties
