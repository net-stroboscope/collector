"""This schedule replication scheduling component."""
import logging

LOG = logging.getLogger(__name__)


class ScheduleReplication(object):
    """Optimize the schedule by replicating slots."""

    def __init__(self, schedule, _, budget):
        # Filter empty slots
        self.schedule = [slot for slot in schedule if slot]
        LOG.info('Min sub-schedule length: %d', len(self.schedule))
        self.budget = budget

    def formulate(self):
        """Nothing specific to formulate."""

    def solve(self):
        """The schedule optimizations replicates slots."""
        # Hard copy the slot as the expansion creates shared refs to the
        # underlying lists
        widen = max(1, int(self.budget.max_slots) / len(self.schedule))
        LOG.info('Replicating the schedule %d times', widen)
        sched = [slot[:] for slot in self.schedule * widen]
        # Add non-multiple slots
        leftovers = self.budget.max_slots - len(sched)
        if leftovers > 0:
            LOG.info('Will add %d unsused slots', leftovers)
            sched.extend([[] for _ in xrange(leftovers)])
        return sched
