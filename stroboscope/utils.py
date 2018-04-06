"""Minor utilities for the framework."""
import threading

from .import ACTIVE_THREADS


class DaemonThread(threading.Thread):
    """Thread that are always daemons."""

    def __init__(self, autostart=False, *args, **kw):
        """Start the thread on creation if autostart is True."""
        super(DaemonThread, self).__init__(*args, **kw)
        self.daemon = True
        if autostart:
            self.start()

    def start(self, *a, **kw):
        """Add self to the active thread list."""
        ACTIVE_THREADS.append(self)
        super(DaemonThread, self).start(*a, **kw)

    def join(self, *a, **kw):
        """Join and remove from the active thread list."""
        super(DaemonThread, self).join(*a, **kw)
        ACTIVE_THREADS.remove(self)
