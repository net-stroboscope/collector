"""This is the path surrounding/region confinement algorithm."""
import itertools
import logging
import networkx as nx

from . import MissingEdge
from .graph import find_path


LOG = logging.getLogger(__name__)


def find_confinement_relaxed(graph, region):
    """
    Find the confinement region with the least amount of rules.

    The version of the confinement algorithm that tries to minimize as much
    as possible the number of mirroring rule while guaranteeing a perfect
    accuracy.

    ! It makes the strong assumption that the confinement region is continguous
    """
    nodes = find_confinement_region(graph, region)
    relaxed_set = set()
    region_set = set(region)
    egresses = graph.egresses.difference(region_set)
    if not egresses:
        LOG.warning('No egresses are defined on the graph! The optimization'
                    ' could potentially remove all locations!')
    # Compute the graph without the Keypoints
    kp_less_graph = nx.DiGraph(graph.edges_iter())
    kp_less_graph.remove_nodes_from(nodes)
    # Compute the keypoint's individual  'contribution' to the connectivity
    edges_for_kp = {kp: list(itertools.chain.from_iterable(
        (graph.in_edges_iter(kp), graph.out_edges_iter(kp)))) for kp in nodes}
    # Remove redundant KP
    keypoint_info = _identify_redundant_nodes(
        kp_less_graph, edges_for_kp, nodes, region_set, egresses)
    # Replace groups of keypoints by equivalent ones
    relaxed_set = _rule_replacement(graph, keypoint_info, egresses,
                                    region_set)
    LOG.debug('%s has a relaxed confinement set given by %s',
              region, relaxed_set)
    return relaxed_set


def _rule_replacement(graph, kp_info, egresses, region):
    # each KP is an individual terminal set
    # egresses are all grouped in the same terminal set
    g = nx.DiGraph(graph.edges_iter())
    region_to_region = [(u, v) for u in g for v in g.neighbors_iter(u)
                        if u in region and v in region]
    g.remove_edges_from(region_to_region)
    disconnected_nodes = [n for n in g if not set(g.neighbors_iter(n))]
    g.remove_nodes_from(disconnected_nodes)
    non_terminals = set(g.nodes_iter())
    terminals = [set([k]) for k in non_terminals.intersection(region)]
    if egresses:
        terminals.append(egresses)
    if len(terminals) < 2:
        LOG.debug('Cannot reduce the keypoint sets if there are less than 2'
                  ' terminal sets!')
        return set(kp_info.iterkeys())
    for t in terminals:
        non_terminals.difference_update(t)
    try:
        return set(NMC(g, terminals, len(kp_info) - 1, non_terminals))
    except NoReduction as e:
        LOG.debug('Could not reduce further the keypoint set! %s', e)
        return set(kp_info.iterkeys())


class NoReduction(Exception):
    """
    There are no possible keypoint reduction.

    The node multiway cut is the keypoint set
    """

    def __init__(self, msg=None):
        """Log the exception when created."""
        LOG.debug('No reduction: %s', msg)
        super(NoReduction, self).__init__(msg)


def NMC(G, terminals, k, non_terminals):
    """
    Find a minimum node multiway cut.

    An adaption of the algorithm to solve the parameterized node
    multiway cut problem from
    "An Improved Parameterized Algorithm for the Minimum Node Multiway Cut
    Problem", J. Chen, Y. Liu, S. Lu, in Algorithmica 55 1-13, Springer, 2009.
    This is polynomial provided k <= log(len(G)), in O(len(G)^3 k 4^k).

    This algorithm identify keypoints by recusively checking that:
    - Keypoints must be placed when two terminal sets are one hop away
    - If the minimal vertex cut between one terminal set and all others is
      bigger than k then we cannot have less than k + 1 keypoints
    - If such a cut exists, then grow one terminal set and check
        * Whether the resulting expanded set still has the same minimal cut,
          meaning that the growed set is valid (and start over)
        * Whether the result expanded set causes the minimal cut to increase,
          meaning that the node is a separator. Attempts to find others
          or signal that we reached an impossible solution.

    Intuitively, this algorithm tries to expand the connected component of each
    keypoint as much as possible, and place keypoints as soon as the connected
    components are one hop away.
    """
    LOG.debug('terminals: %s', terminals)
    # 1. If an edge has its two ends in two different terminal sets
    for u, v in G.edges_iter():
        v_set = u_set = None
        for t in terminals:
            if u in t:
                u_set = t
            if v in t:
                v_set = t
            if u_set is not None and v_set is not None and v_set is not u_set:
                # return no.
                raise NoReduction("One edge has ends in two different terminal"
                                  " sets: %s->%s and %s->%s" %
                                  (u, u_set, v, v_set))
    # 2. If a non-terminal w has two neighbors in two different terminal sets
    for w in non_terminals:
        nei = set(G.neighbors_iter(w))
        neighbouring_terminals_count = 0
        for t in terminals:
            if nei.intersection(t):
                neighbouring_terminals_count += 1
            if neighbouring_terminals_count > 1:
                # return w + NMC(G - w, {T1 ... Tl}, k)
                g_minus_w = __copy_graph_remove_node(G, w)
                LOG.debug('%s has multiple neighbors in different terminal '
                          'sets', w)
                result = NMC(g_minus_w, terminals, k - 1,
                             non_terminals.difference(set([w])))
                # if result is "no", we will forget w due to the exception
                result.append(w)
                return result
    # 3. find the size m1 of a minimum V-cut between T1 and U_j^l Tj
    t1 = terminals[0]
    t2_l = terminals[1:]
    t2_l_flat = list(itertools.chain.from_iterable(t2_l))
    try:
        m1 = __bounded_minimal_vertex_cut(G, t1, t2_l_flat, k)
    except CutTooBig:
        # 4. if m1 > k: return "no"
        raise NoReduction("The minimum V-cut is too big")
    tlen = len(terminals)
    if m1 == 0:
        LOG.debug('m1 = %d and tlen = %d', m1, tlen)
        # 5. if m1 = 0 and l = 2: return []
        if tlen == 2:
            return []
        # 5.1 if m1 = 0 and l > 2: return NMC (G, {T2 ... Tl}, k)
        if tlen > 2:
            return NMC(G, t2_l, k, non_terminals)
    # 6. pick a non-terminal u that has a neighbor in T1
    u = non_terminals.intersection(set(itertools.chain.from_iterable(
        G.neighbors_iter(t) for t in t1))).pop()
    # let T1' = T1 + u
    u_set = set([u])
    t1_prime = t1.union(u_set)
    non_terminals_minus_u = non_terminals.difference(u_set)
    try:
        # 6.1 If the size of a min V-cut between t1' and U^l_j=2 Tj = m1
        if __bounded_minimal_vertex_cut(G, t1_prime, t2_l_flat, m1) == m1:
            # return NMC(G, {T1', T2 ... Tl}, k
            LOG.debug('%s kept the same V-cut', u)
            t2_l.insert(0, t1_prime)
            return NMC(G, t2_l, k, non_terminals_minus_u)
        else:
            raise RuntimeError("[BUG] Adding a node to a terminal set cannot "
                               "reduce its minimum cut size!!!")
    except CutTooBig:
        # if adding u to t1 increase the cut size, then u is a separator
        pass
    g_minus_u = __copy_graph_remove_node(G, u)
    try:
        # 6.2 ,S = u + NMC(G - u, {T1 ... Tl}, k - 1)
        S = NMC(g_minus_u, terminals, k - 1, non_terminals_minus_u)
        S.append(u)
        LOG.debug('%s had a valid sub-solution', u)
        # if S is not "no" return S (i.e. no exception raised)
        return S
    except NoReduction:
        # 6.3 return NMC(G, {T1', T2 ... Tl}, k)
        LOG.debug('Swapping T1 for T1 + %s', u)
        t2_l.insert(0, t1_prime)
        return NMC(G, t2_l, k, non_terminals_minus_u)


def __copy_graph_remove_node(orig_g, remove_node):
    g = nx.DiGraph(orig_g.edges_iter())
    g.add_nodes_from(orig_g.nodes_iter())
    g.remove_node(remove_node)
    return g


class CutTooBig(Exception):
    """The minimal vertex cut if bigger than the provided bound."""


def __bounded_minimal_vertex_cut(base_graph, src, dst, k):
    """Search a the minimal vertex cut."""
    # Copy the graph as we'll collapse src/dst sets
    g = nx.DiGraph(base_graph.edges_iter())
    g.add_nodes_from(base_graph.nodes_iter())
    s = __merge_nodes(g, src)
    t = __merge_nodes(g, dst)
    for u, v, data in g.edges_iter(data=True):
        data['used_flow'] = 0
        if not g.has_edge(v, u):
            g.add_edge(v, u, used_flow=1)

    g_pred = g.pred
    g_succ = g.succ

    def _predicate(attr):
        return attr['used_flow'] < 1

    flow_value = 0
    while flow_value <= k:
        # Find an augmenting path
        path = find_path((g_succ, g_pred), s, t, predicate=_predicate)
        if not path:
            # We found the minimal cut
            break
        # Augment flow along the path.
        it = iter(path)
        u = next(it)
        for v in it:
            g_succ[u][v]['used_flow'] += 1
            g_succ[v][u]['used_flow'] -= 1
            u = v
        flow_value += 1
    if flow_value > k:
        raise CutTooBig("The V-cut is larger than k")
    return flow_value


def __merge_nodes(g, nodes):
    """Contract the nodes from the graph to a single one."""
    if len(nodes) <= 1:
        return list(nodes).pop()
    into = '_'.join(itertools.imap(str, nodes))
    _in = ((u, into) for u, _ in g.in_edges(nodes))
    _out = ((into, v) for _, v in g.out_edges(nodes))
    edges = itertools.chain(_in, _out)
    g.add_edges_from(edges)
    g.remove_nodes_from(nodes)
    return into


def _identify_redundant_nodes(kp_less_graph, edges_for_kp, nodes, region_set,
                              egresses):
    """
    Identify key points that are redundant.

    From a graph where the
    region has been disconnected, add back all keypoints one by one, then
    look whether they reconnect back the region to:
    - one or more egress(es)
    - the region itself through the keypoint (i.e. the keypoint connects 2
      different nodes from the region)
    """
    node_info = {}
    for kp in nodes:
        # Add back the keypoint to check to the graph
        kp_less_graph.add_edges_from(edges_for_kp[kp])
        # The connected component of the keypoint (beside the region)
        cc = set()
        to_visit = set([kp])
        # What connectivity does this keypoint prevents?
        _reachability_set = set()
        while to_visit:
            n = to_visit.pop()
            if n in cc:
                # We already covered this node through another one
                # As we assume that the control-plane is correct, this does not
                # matter (i.e. we have an 'inner loop')
                continue
            cc.add(n)
            nei = set(kp_less_graph.neighbors_iter(n))
            # Track connections looping back to the region as to be prevented
            _reachability_set.update(nei.intersection(region_set))
            # Keep exploring the connected component outside the region
            to_visit.update(nei.difference(region_set))
        # Track egresses part of the connected component
        _reachability_set.update(egresses.intersection(cc))
        # The keypoint is needed if it prevents connectivity between multiple
        # nodes of interest (i.e. egress-to-region or region-to-region)
        if len(_reachability_set) > 1:
            LOG.debug('%s acts as separator between %s', kp, _reachability_set)
            node_info[kp] = (cc, _reachability_set)
        else:
            LOG.debug("%s is redundant as it only connects to '%s'",
                      kp, _reachability_set.pop())
        # Restore the graph state
        kp_less_graph.remove_node(kp)
    return node_info


def find_confinement_region(graph, region):
    """
    Find the nodes surrounding a region.

    Find all the routers which have to install passive rules to confine
    a region.

    :param graph: The current network graph
    :param region: The list of node forming the region that should be confined.
                   These nodes must form a connected subgraph!
    """
    edges = find_confinement_edges(graph, region)
    # Only keep the destination node from the edges, i.e. the surrounding set
    # of the region.
    confinement_set = set([v for _, v in edges])
    LOG.debug('%s is confined by %s', region, confinement_set)
    return confinement_set


def find_confinement_edges(graph, region):
    """
    Find the set of edges surrounding a region.

    Find all the edges which have to install passive rules to confine
    a region.

    :param graph: The current network graph
    :param region: The list of node forming the region that should be confined.
                   These nodes must form a connected subgraph!
    """
    confinement_set = set()
    region_set = set(region)
    for node in region:
        n_set = set(graph.neighbors_iter(node))
        if not n_set.intersection(region_set):
            raise MissingEdge(graph, node)
        confinement_set.update([(node, v)  # Omit all region-region links
                                for v in n_set.difference(region_set)])
    LOG.debug('%s is edge-confined by %s', region, confinement_set)
    return confinement_set


# Ordered from least optimised to most
CONFINE_OPT = [find_confinement_edges, find_confinement_region,
               find_confinement_relaxed]
