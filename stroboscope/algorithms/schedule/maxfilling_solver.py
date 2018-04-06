"""
This module implements the maximal filling step of the scheduling pipeline,
which attempts to squeeze as many queries as possible in the remaining leftover
budget space.
"""
import logging

import gurobipy as grb

from ._common import Solver

LOG = logging.getLogger(__name__)


class MaxFilling(Solver):
    """Implements the optimal MaxFilling part of the scheduling pipeline."""

    def __init__(self, schedule, queries, budget):
        self.mapper = _SlotMapper(schedule, queries, budget)
        super(MaxFilling, self).__init__(queries, budget,
                                         len(self.mapper.new_schedule))

    def query_can_belong_in_slot(self, q, s):
        """
        Override to exclude queries already present in the slot or too large.
        """
        return not self.mapper.query_in_slot(q, s) and q.cost <= self.using(s)

    def using(self, s):
        """Override to adjust on a slot basis."""
        return self.mapper.left_in_slot(s)

    def formulate(self):
        """Register the additional variable."""
        self.alloc_min = self.prob.addVar(name="M")
        super(MaxFilling, self).formulate()

    def formulate_model(self, prob):
        """Formulate the ILP."""
        R = self.R.__getitem__
        for s in self._forall_s():
            indexes = list(self.indexes(s=s))
            prob.addConstr(grb.LinExpr(self.a_qs(indexes),
                                       [R(idx) for idx in indexes]
                                       ) <= self.using(s))
        # Vq sum_s R_qs >= alloc_min
        for q in self._forall_q():
            queries = [self.R[idx] for idx in self.indexes(q=q)]
            ones = [1] * len(queries)
            prob.addConstr(grb.LinExpr(ones + [-1],
                                       queries + [self.alloc_min]) >= 0)
        # max[ sum_q (sum_s R_qs) w_q + m sigma ]
        idx = list(self.indexes())
        prob.setObjective(
            grb.LinExpr(self.w_qs(idx) + [self._budget.sigma],
                        map(self.R.__getitem__, idx) + [self.alloc_min]),
            sense=grb.GRB.MAXIMIZE)

    def extract_solution(self):
        """Reconstruct the global schedule."""
        for (q, s), var in self.R.iteritems():
            if var.x:
                self.mapper.real_slot(s).add(self._queries[q])
        return [list(slot_set) for slot_set in self.mapper.schedule]


class _SlotMapper(object):
    def __init__(self, schedule, queries, budget):
        self.schedule = [set(slot) for slot in schedule]
        self.queries = queries
        self.budget = budget
        self.new_schedule = []
        self.new_schedule_mapping = {}
        self._build_mapping()

    def _build_mapping(self):
        # Find min-sized queries
        min_using = min(self.budget.using,
                        min([q.cost for q in self.queries if q.cost > 0]))
        # Compute slot free space
        for idx, slot in enumerate(self.schedule):
            left = self.budget.using - sum(q.cost for q in slot)
            if left - min_using <= 0:
                # Not enough space for anything, ignore the slot
                continue
            self.new_schedule_mapping[
                len(self.new_schedule_mapping)] = (left, idx)

    def real_slot(self, s):
        """Real slot for a mapped slot."""
        return self.schedule[self.new_schedule_mapping[s][1]]

    def left_in_slot(self, s):
        """How much bandwidth leftover for a given slot."""
        return self.new_schedule_mapping[s][0]

    def query_in_slot(self, q, s):
        return q in self.real_slot(s)
