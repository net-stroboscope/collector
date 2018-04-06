"""
This module defines the different scheduling pipelines that can be used to
finalize the measurement campaign.
"""
import time
import logging

from ._common import NoSchedule
from .binp_solver import BINPSolver
from .maxfilling_solver import MaxFilling
from .first_fit import FirstFitSolver
from .replication import ScheduleReplication


LOG = logging.getLogger(__name__)


class _AbstractPipeline(object):
    def __init__(self, min_subschedule, budget_maximization, queries, budget):
        self.minsub = min_subschedule(queries, budget)
        self.bmax = budget_maximization
        self.budget = budget
        self.queries = queries

    def formulate(self):
        """Formulate the scheduling problems."""
        # Stop at the first one as others depend on it
        self.minsub.formulate()

    def solve(self):
        """Return the schedule solution."""
        elapsed = -time.time()
        sched = self.minsub.solve()
        elapsed += time.time()
        for solver in self.bmax:
            s = solver(sched, self.queries, self.budget)
            s.formulate()
            try:
                e = -time.time()
                sched = s.solve()
                elapsed += (e + time.time())
            except NoSchedule:
                LOG.info('Cannot optimize further than %s', solver.__name__)
                break
        return sched


class ApproximateSchedule(_AbstractPipeline):
    """FFD + replication."""

    def __init__(self, queries, budget):
        super(ApproximateSchedule, self).__init__(FirstFitSolver,
                                                  [ScheduleReplication],
                                                  queries, budget)


class HalfApproximateSchedule(_AbstractPipeline):
    """FFD + replication + max filling."""

    def __init__(self, queries, budget):
        super(HalfApproximateSchedule, self).__init__(FirstFitSolver,
                                                      [ScheduleReplication,
                                                       MaxFilling],
                                                      queries, budget)


class OptimizedSchedule(_AbstractPipeline):
    """FFD + bin-packing + replication + max filling."""

    def __init__(self, queries, budget):
        super(OptimizedSchedule, self).__init__(BINPSolver,
                                                [ScheduleReplication,
                                                 MaxFilling],
                                                queries, budget)
