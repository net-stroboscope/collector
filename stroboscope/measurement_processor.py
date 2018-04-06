"""Sample measurement processors that consume measurement campaign results."""
import logging
LOG = logging.getLogger(__name__)


class MeasurementProcessor(object):
    """Output to stdout all measurement results."""

    def start(self):
        """Notify this object that the measurement campaign starts."""

    def process(self, locations, queries, traffic_slices):
        """
        Consume results from a measurement campaign.

        :locations: dict giving query->mirroring rules
        :queries: all queries for the measurement campaign
        :traffic_slices: a list of dict keyed by router name,
                         containing the traffic slice of that router
        """

    def stop(self):
        """Stop the measurement consumer."""
