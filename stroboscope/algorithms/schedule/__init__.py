"""The scheduling pipeline implementation for different optimization levels."""
import logging

from .binp_solver import BINPSolver
from .scheduling_pipeline import (ApproximateSchedule, OptimizedSchedule,
                                  HalfApproximateSchedule)
from .first_fit import FirstFitSolver
from ._common import NoSchedule

LOG = logging.getLogger(__name__)


# All possible optimisation levels
FUNCS = {'first-fit-decreasing': FirstFitSolver,
         'bin-packing': BINPSolver,
         'approximation': ApproximateSchedule,
         'half-approximation': HalfApproximateSchedule,
         'optimized': OptimizedSchedule}


def balance_and_schedule(queries, budget, function='approximation'):
    """
    Decide the accuracy levels to use for each query and schedule them.

    :queries: The list of queries to consider
    :budget: Their associated budget
    :return: {q: [s, ...]} the slots for every query
    """
    LOG.info('Scheduling using the %s pipeline', function)
    solver = FUNCS[function](queries, budget)
    solver.formulate()
    solution = solver.solve()
    return solution


__all__ = ['balance_and_schedule', 'NoSchedule', 'FUNCS']
