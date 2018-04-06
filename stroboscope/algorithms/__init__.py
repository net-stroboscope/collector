"""Common module Errors and checks."""
from itertools import izip


class MissingEdge(Exception):
    """Indicates that a graph has a missing edges."""

    def __init__(self, g, u, v=None):
        """
        Register the edges that is missing from the graph.

        :g: The graph that has the missing edge
        :u: the node missing an edge
        :v: possibly the missing edge end point
        """
        self.g = g
        self.u = u
        self.v = v
        super(MissingEdge, self).__init__()

    def __repr__(self):
        """Override to display to edge."""
        return '<MissingEdge %s in %s>' % (('(%s,%s)' % (self.u, self.v))
                                           if self.v else 'starting from %s' %
                                           self.u, self.g.name)


def check_graph_supports_path(graph, path):
    """
    Check that a given path is feasible in the graph.

    :return: True
    :raise: MissingEdge
    """
    for x, y in izip(path, path[1:]):
        if not graph.has_edge(x, y):
            raise MissingEdge(graph, x, y)
