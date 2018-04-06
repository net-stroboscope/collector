"""Misc. graph algorithms."""
import itertools
import heapq
import sys
import operator


def find_path(g, s, t, predicate=None):
    """
    Find a path from s to t, according to an optional predicate.

    :g: the graph to search, or a tuple (successor_dict, predecessor_dict)
    :s: the source node of the path
    :t: the destination node of the path
    :predicate: a function receiving the attribute of the current node in order
                to evaluate whether it can be included in the path or not
    """
    if s == t:
        return [s]
    n, pred, succ = __bdfs(g, s, t, predicate)
    if pred is None:
        return []
    path = [n]
    u = n
    while u != s:
        u = pred[u]
        path.append(u)
    path.reverse()
    u = n
    while u != t:
        u = succ[u]
        path.append(u)
    return path


def __bdfs(g, s, t, predicate=lambda x: True):
    """Perform a BDFS in the graph."""
    pred = {s: None}
    q_s = [s]
    succ = {t: None}
    q_t = [t]
    try:
        g_succ, g_pred = g
    except ValueError:
        g_succ = g.succ
        g_pred = g.pred
    while True:
        q = []
        if len(q_s) <= len(q_t):
            for u in q_s:
                for v, attr in g_succ[u].iteritems():
                    if v not in pred and predicate(attr):
                        pred[v] = u
                        if v in succ:
                            return v, pred, succ
                        q.append(v)
            if not q:
                return None, None, None
            q_s = q
        else:
            for u in q_t:
                for v, attr in g_pred[u].iteritems():
                    if v not in succ and predicate(attr):
                        succ[v] = u
                        if v in pred:
                            return v, pred, succ
                        q.append(v)
            if not q:
                return None, None, None
            q_t = q


"""Backported code from fibbingnode.misc.igp_graph under GPLv2
See github.com/Fibbing/fibbingnode/fibbingnode/misc/igp_graph.py"""


def get_spt(g, cost_key):
    """
    Return the shortest path tree in the graph.

    :g: the graph to inspect
    :cost_key: the edge attribute giving their weight, which is 1 if unset
    :return: {u: {v: spt(u, v)}}
    """
    dist = {}
    spt = {}
    for n in g.nodes_iter():
        spt[n], dist[n] = _spt_from_src(g, n, cost_key)
    return spt, dist


def _spt_from_src(g, source, cost_key):
    # Adapted from single_source_dijkstra in networkx
    dist = {}  # dictionary of final distances
    paths = {source: [[source]]}  # dictionary of list of paths
    seen = {source: 0}
    fringe = []
    c = itertools.count()  # We want to skip comparing node labels
    heapq.heappush(fringe, (0, next(c), source))
    _get_w = operator.methodcaller('get', cost_key, 1)
    _pop = heapq.heappop
    _push = heapq.heappush
    while fringe:
        (d, _, v) = _pop(fringe)
        if v in dist:
            continue  # already searched this node.
        dist[v] = d
        for w, edgedata in g[v].iteritems():
            vw_dist = d + _get_w(edgedata)
            seen_w = seen.get(w, sys.maxint)
            if vw_dist < dist.get(w, 0):
                raise ValueError('Contradictory paths found: '
                                 'negative metric?')
            elif vw_dist < seen_w:  # vw is better than the old path
                seen[w] = vw_dist
                _push(fringe, (vw_dist, next(c), w))
                paths[w] = list(extend_paths_list(paths[v], w))
            elif vw_dist == seen_w:  # vw is ECMP
                paths[w].extend(extend_paths_list(paths[v], w))
            # else w is already pushed in the fringe and will pop later
    return paths, dist


def extend_paths_list(paths, n):
    """
    Return and iterator on a new set of paths.

    built by copying the original paths
    and appending a new node at the end of it
    """
    for p in paths:
        yield p[:] + [n]
