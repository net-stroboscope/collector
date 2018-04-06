"""An optimal bin-packing solver."""
import logging
import gurobipy as grb

from ._common import Solver
from .first_fit import find_first_fit_estimation

LOG = logging.getLogger(__name__)


class BINPSolver(Solver):
    """A bin-packing ILP implementation that will do an exhaustive search."""

    def __init__(self, queries, budget):
        # First compute an upper to the sub-problem
        upper_bound = find_first_fit_estimation(queries, budget)
        super(BINPSolver, self).__init__(queries, budget, len(upper_bound))
        self.Y = None

    def formulate(self):
        """Register the additional variable."""
        self.Y = {s: self.prob.addVar(lb=0.0, ub=1.0, vtype=grb.GRB.BINARY,
                                      name="Y_%d" % s)
                  for s in self._forall_s()}
        super(BINPSolver, self).formulate()

    def formulate_model(self, prob):
        """Formulate the ILP."""
        R, Y = self.R.__getitem__, self.Y.__getitem__
        # C1
        # Vq sum_s R_qs == 1
        for q in self._forall_q():
            queries = [R(qs) for qs in self.indexes(q=q)]
            ones = [1] * len(queries)
            prob.addConstr(grb.LinExpr(ones, queries) == 1)
        # C2
        # Vs sum_q R_qs a_q <= beta Y_s
        for s in self._forall_s():
            indexes = list(self.indexes(s=s))
            prob.addConstr(grb.LinExpr(
                self.a_qs(indexes) + [-self.using(s)],
                [R(idx) for idx in indexes] + [Y(s)]) <= 0)
        # C3
        # Vs Vq: Y_s >= R_qs
        for s, yvar in self.Y.iteritems():
            for q in self.indexes(s=s):
                prob.addConstr(grb.LinExpr([1, -1], [yvar, R(q)]) >= 0)
        # Tie-breaking constraints
        # Ys >= Y_s+1
        for s in self._forall_s(1):
            prob.addConstr(grb.LinExpr([1, -1], [Y(s - 1), Y(s)]) >= 0)
        # Objective function
        # min[ sum_s Y_s ]
        prob.setObjective(
            grb.LinExpr([1] * len(self.Y), self.Y.values()),
            sense=grb.GRB.MINIMIZE)
