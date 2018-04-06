"""Globals for the whole framework."""

# Flag indicating whether the framework is running or not
RUNNING = True
# All threads used throughout the framework and managed by the collector
ACTIVE_THREADS = []
# The backend to use to activate mirroring on router
RULE_BACKEND = None


def join():
    """Wait for all threads in the framework to complete."""
    global RUNNING
    RUNNING = False
    if RULE_BACKEND:
        RULE_BACKEND.close()
    for t in ACTIVE_THREADS:
        t.join()
