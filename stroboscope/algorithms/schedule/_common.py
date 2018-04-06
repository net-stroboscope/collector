"""Common scheduling definitions."""
import logging

import gurobipy as grb

LOG = logging.getLogger(__name__)


DEBUG_GUROBI = False


class NoSchedule(ValueError):
    """The schedule is not feasible with the selected solver."""


class Solver(object):
    """Plumbing to build and solve the decision and scheduling ILP"""

    def __init__(self, queries, budget, max_timeslots=None):
        """Initialize the solver parameters

        :queries: The list of queries to consider
        :budget: The monitoring budget
        """
        if not DEBUG_GUROBI:
            grb.setParam("OutputFlag", 0)
        grb.setParam('MIPGap', budget.mip_gap)
        self._queries = queries
        self._budget = budget
        self.max_timeslots = (max_timeslots if max_timeslots is not None else
                              budget.max_slots)
        LOG.debug('Max timeslot count: %d', self.max_timeslots)
        self.prob = grb.Model('Query scheduling and accuracy decision')
        self.prob.Params.TimeLimit = budget.max_ilp_run

    def formulate(self):
        """Formulate the ILP problem."""
        m = self.prob
        self.R = {(q, s): m.addVar(
            lb=0.0, ub=1.0, vtype=grb.GRB.BINARY,
            name='R_%d_%d' % (q, s)) for q, s in self.indexes()}
        # Register all variables etc
        m.update()
        # Callback constraints definition
        self.formulate_model(m)
        # Update the model again to reflect the changes
        m.update()

    def formulate_model(self, prob):
        """Add constraints and objective function to the model."""

    def _actual_solve(self):
        self.prob.optimize()

    def solve(self):
        """Solve the formulated ILP and return the slots for every query. """
        self._actual_solve()
        if self.prob.status != grb.GRB.status.OPTIMAL:
            raise NoSchedule('Could not find a solution! <Guroby error: %s>' %
                             self.prob.status)
        return self.extract_solution()

    def extract_solution(self):
        """Explore the model and return the list of slots and their queries."""
        result = [[] for _ in self._forall_s()]
        for (q, s), var in self.R.iteritems():
            if var.x:
                result[s].append(self._queries[q])
        return [slot for slot in result if slot]

    def a_q(self, q):
        """Return the active bandwidth query q"""
        return self._queries[q].cost

    def a_qs(self, it):
        """Return a list of a_q values from the iterator"""
        return [self.a_q(q) for q, _ in it]

    def w_q(self, q):
        """Return the weight for query q"""
        return self._queries[q].weight

    def w_qs(self, it):
        """Return a list of w_q values from the iterator"""
        return [self.w_q(q) for q, _ in it]

    def using(self, s):
        """The available budget in slot s."""
        return self._budget.using

    def _forall_q(self):
        """Return an iterator over all queries"""
        return xrange(len(self._queries))

    def _forall_s(self, start=0):
        """Return an iterator over all time slot number."""
        return xrange(start, self.max_timeslots)

    def query_can_belong_in_slot(self, q, s):
        """Return whether the query q could be assigned in slot s."""
        return True

    def indexes(self, q=None, s=None):
        """Return all variable indexes for a given slot and/or query."""
        q_iter = (q,) if q is not None else self._forall_q()
        s_iter = (s,) if s is not None else tuple(self._forall_s())
        for q in q_iter:
            for s in s_iter:
                if self.query_can_belong_in_slot(q, s):
                    yield q, s
