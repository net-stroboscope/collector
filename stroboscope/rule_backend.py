"""The currently supported backends to trigger mirroring."""
import logging

from paramiko.client import SSHClient, SSHException, AutoAddPolicy

LOG = logging.getLogger(__name__)


class _RuleBackend(object):
    """The base of the backends: ssh sessions manager."""

    # How should we start the daemon that will activate/stop mirroring rules
    DAEMON_STARTUP_LINE = None
    # All opened SSH sessions to routers
    SESSIONS = {}
    # The name of the SSH key to use to reach routers.
    SSH_KEY = None
    # The username
    USER = 'root'
    # The minimal slot duration for this backend
    MIN_SLOT_DURATION = 1000  # ms
    # The address of the collector
    COLLECTOR_ADDRESS = None
    # The tunnel encapsulation destination
    ENCAP_ADDRESS = None

    @classmethod
    def _connect(cls, location):
        LOG.debug('Opening SSH connection towards %s', location)
        handle = SSHClient()
        handle.set_missing_host_key_policy(AutoAddPolicy())
        handle.connect(location, key_filename=cls.SSH_KEY, username=cls.USER)
        try:
            stdin, stdout, stderr = handle.exec_command(
                cls.DAEMON_STARTUP_LINE.format(
                    collector_address=cls.COLLECTOR_ADDRESS,
                    source_address=location,
                    encap_address=cls.ENCAP_ADDRESS))
            stdout.close()
            stderr.close()
            return handle, stdin
        except SSHException as e:
            LOG.error('Failed to activate a rule on %s: %s', location, e)
            handle.close()
            return None, None

    @classmethod
    def connect(cls, location):
        """Return a connection to a given router."""
        try:
            return cls.SESSIONS[location]
        except KeyError:
            handle = cls._connect(location)
            cls.SESSIONS[location] = handle
            return handle

    @classmethod
    def activate(cls, location, rules, duration):
        """Activate a mirroring rule and return whether it was succesfull."""
        try:
            _, stdin, stderr = cls.connect(location)
            stdin.write('%f %s\n' % (duration, ' '.join(
                '%s|%s' % (r.interface, r.prefix) for r in rules)))
            stdin.flush()
            return True
        except ValueError:
            return False

    @classmethod
    def register_connection_properties(cls, ssh_filename=None,
                                       username='root'):
        """Register properties of SSH sessions."""
        cls.SSH_KEY = ssh_filename
        cls.USER = username

    @classmethod
    def close(cls):
        """Shutdown all SSH connections."""
        for h in cls.SESSIONS.values():
            h[0].close()


class LinuxBackend(_RuleBackend):
    """A Linux router using IPtables."""

    # possible extension would be to leverage XDP
    DAEMON_STARTUP_LINE = ('/bin/stroboscope-linux-backend '
                           '%{collector_address}s %{source_address}s '
                           '%{encap_address}s')
    MIN_SLOT_DURATION = 25


class IOSBackend(_RuleBackend):
    """A Cisco router using the python API."""

    DAEMON_STARTUP_LINE = 'source stroboscope-ios-backend'
    MIN_SLOT_DURATION = 23  # cfr. measurements on Cisco C7018
