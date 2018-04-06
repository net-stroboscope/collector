"""This module implements the FFD heuristic to compute schedules."""
import logging

from ._common import NoSchedule

LOG = logging.getLogger(__name__)


class FirstFitSolver(object):
    """Wrapper around the FFD heristics."""

    def __init__(self, queries, budget):
        """Register the inputs."""
        self.queries = queries
        self.budget = budget

    def formulate(self):
        """We have nothing to formulate."""

    def solve(self):
        """Delegate to the general formulation."""
        return find_first_fit_estimation(self.queries, self.budget)


def find_first_fit_estimation(queries, budget):
    """Find a suitable schedule using a first-fit-decreasing approach."""
    max_bw = budget.using
    slots = [[[], 0]]  # a slot is (queries, consumed BW)

    left = sorted([(q.cost, q) for q in queries])

    while left:
        cost, q = left.pop()
        for slot in slots:
            new_bw = slot[1] + cost
            if new_bw <= max_bw:
                # Add the query in the first fitting slot
                slot[0].append(q)
                slot[1] = new_bw
                break
        else:
            if len(slots) >= budget.max_slots:
                raise NoSchedule(
                    'FFD requires too many slots (%d out of %d)!' % (
                        len(slots), budget.max_slots))
            slots.append([[q], cost])

    LOG.info('Found a first fit decreasing solution over %d bins', len(slots))

    return [qlist for qlist, _ in slots]
