"""This module implements the KPS algorithm."""
import logging

from . import check_graph_supports_path


LOG = logging.getLogger(__name__)


def _precond(graph, original_path):
    length = len(original_path)
    # path too small
    if length <= 2:
        LOG.debug('No optimization possible, path is too short')
        return False, [(h, 1) for h in original_path]
    # check if original path exists in graph. This is MANDATORY for the
    # algorithm to work
    check_graph_supports_path(graph, original_path)
    return True, length


def find_key_points(graph, original_path):
    """
    Find the keypoints to sample for the path on the graph.

    :graph: _complete_ network graph
    :original_path: the path to sample
    """
    status, default_solution = _precond(graph, original_path)
    if not status:
        return default_solution
    # Try the different possibilities, smallest ones first
    q = [(len(kpset), kpset) for kpset in _all_kp_possible(original_path)]
    q.sort(reverse=True)
    memo = set()
    reject = set()
    while q:
        _, possible_kp = q.pop()
        for p in possible_kp:
            length = len(p)
            src, dst = endp = _path_endpoints(p)
            if length <= 2 or endp in memo:
                # Too short or already seen, always valid
                continue
            elif endp in reject:
                # We already explored this subpath and rejected it
                break
            elif _paths_for_len(graph, src, dst, length - 1):
                # p has a unique length
                memo.add(endp)
            else:
                # Multiple equal-length paths, ignore this solution
                reject.add(endp)
                break
        else:  # reached only if the loop completed
            return _extract_keypoints(possible_kp, original_path)
    # This is theoritically impossible to reach, as
    # (i) _precond will exit early for paths too short
    # (ii) every path can be sampled by looking at every node ... i.e. there is
    #      always a solution -> reaching this is a bug!
    raise RuntimeError('No solution found after Keypoints sampling !')


def _all_kp_possible(l):
    """Find all subpaths decompositions."""
    # O (l * log(l))
    _len = len(l)
    if not l or _len < 2:
        yield []
    elif _len >= 2:
        for i in range(2, _len + 1):
            for p in _all_kp_possible(l[i - 1:]):
                yield [l[:i]] + p


def _extract_keypoints(paths, original_path):
    kp = []
    LOG.debug('Map %s from %s', paths, original_path)
    for p in paths:
        start, end = _path_endpoints(p)
        kp.append((start,
                   original_path.index(end) - original_path.index(start)))
    kp.append((original_path[-1], 0))
    LOG.debug('%s was reduced to %s', original_path, kp)
    return kp


def _path_endpoints(p):
    return p[0], p[-1]


def _paths_for_len(g, src, dst, l):
    """
    Return if there are multiple paths of a given length between two location.

    :return: whether there are less than max_cnt paths

    This function is *tricky*:
    We want to compute simple paths from src to dst, and assert whether there
    is more than one. Because of this, we cannot rely on a subpath
    decomposition (i.e. count the number of path from our neighbour) as
    we have another visited/exclusion set to prevent the loops. This prevents
    us from using the memo set as well, and also from storing partial results
    (again, because they might be 'ok', but only as a result of the currently
    evaluated path that breaks a loop)
    """
    visited = [src]
    stack = [iter(g[src])]
    cnt = 0
    # O(n^k)
    while stack and cnt < 2:
        children = stack[-1]
        child = next(children, None)
        _len_diff = l - len(visited)
        if child is None:
            # Explored all neighbors, backtrack
            stack.pop()
            visited.pop()
        elif _len_diff > 0:
            # Grow the path iff no loop && not dest
            if child not in visited and child != dst:
                visited.append(child)
                stack.append(iter(g[child]))
            # else: consume the child
        else:
            # We do not consider multigraph, i.e. max(edgecount(u, v)) <= 1
            if child == dst or dst in children:
                # We found a path to the dest of the expected len
                cnt += 1
            # else: consume the child
    LOG.debug('Found %d paths of length %d from %s to %s', cnt, l, src, dst)
    return cnt < 2


def find_key_points_segment_spt(graph, original_path):
    """
    Find key-points in a given path for the key-point sampling algorithm.

    :param graph: the current network graph
    :param original_path: the original path as a list of router names
    :return: returns the key-points as a list of tuples (node, gap),
             where the gap is the number of hops after node until the next one
             included, i.e. if we can remove C, we can transform:
             [A, B, C, D] -> [(A, 1), (B, 2), (D, X)]
             The gap has _no_ meaning for the last hop
    """
    status, length = _precond(graph, original_path)
    if not status:
        return length
    spt = graph.edge_spt
    # initial values
    segment_end = start = 0
    # Store first point, without any gap by definition
    new_path = []
    while start < length:
        segment_end = _segment_path(original_path, start, spt, length) - 1
        new_path.append((original_path[start], segment_end - start))
        start = segment_end
    # Otherwise the end was added at the last gap reset
    LOG.debug('%s is reduced to key points: %s', original_path, new_path)
    return new_path


def _segment_path(p, start, spt, max_len):
    """
    Return the starting index of the next segment.

    I.e. the index of the path element that is no longer covered by the
    edge-shortest path.
    This is lesser or equal to max_len
    """
    # the single-edge path is always the shortest one
    end = start + 2
    while end < max_len:
        ps = spt[p[start]][p[end]]
        if len(ps) > 1:
            # Multiple disjoint shortest paths
            return end
        if ps[0] != p[start:end + 1]:
            # There exists a path shorter than the current one
            return end
        end += 1
    return end


# From least optimized to most
KPS_OPT = [find_key_points_segment_spt, find_key_points]
