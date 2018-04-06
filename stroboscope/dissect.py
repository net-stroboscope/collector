"""Packet dissectors decapsulate mirrored GRE packets."""
import socket
import logging

from ipaddress import ip_interface, ip_address

import stroboscope as core
from .utils import DaemonThread
from ._dissect import Dissector as _Dissector, error as _error

LOG = logging.getLogger(__name__)


class RecvError(Exception):
    """Signal an error when receiving packets."""


class Dissector(object):
    """Listen and dissect mirrored packets."""

    def __init__(self, rdict, bind_on=u'0.0.0.0', callback=lambda pkt: None):
        """
        Register the new socket tap.

        :param rdict: A function returning a node name from its IP address
        :param bind_on: The address on which the dissector should bind
        :param callback: a one argument function that gets called at each
                         received packet (the argument),
                         i.e. <Queue instance>.put
        """
        s = self.sock = socket.socket(socket.AF_INET,
                                      socket.SOCK_RAW,
                                      socket.IPPROTO_GRE)
        self.d = _Dissector(sfd=s.fileno())
        self.callback = callback
        self.rdict = rdict
        self._aux_thread = None
        self._ip = ip_interface(bind_on).ip.compressed
        # The number of recv errors we tolerate before exiting
        self.err_threshold = 5
        s.bind((self._ip, 0))

    def recv(self):
        """
        Block until a packet has been received.

        :raise: RcvError
        """
        try:
            data = self.d.recv()
            if not data:
                return
            p = Packet.from_dissector(data, self.rdict)
            self.callback(p)
        except (_error, OSError, ValueError) as e:
            raise RecvError(str(e))

    def listen(self):
        """Listen indefinitely for incoming packet in a new thread."""
        self._aux_thread = DaemonThread(target=self._listen, autostart=True)

    def _listen(self):
        LOG.info('Listening indefinitely on %s', self._ip)
        err_count = 0
        while core.RUNNING:
            try:
                self.recv()
            except RecvError as e:
                err_count += 1
                if err_count <= self.err_threshold:
                    LOG.warning('Caught exception when receving mirrored '
                                'traffic (%d/%d): %s', e, err_count,
                                self.err_threshold)
                else:
                    break
        LOG.warning('Stopped listening for mirrored traffic')
        self.sock.close()

    def __str__(self):
        """Display the listen IP address."""
        return '<Dissector listening on %s>' % self._ip


class Packet(object):
    """
    Information about a mirrored packet.

    Useful members include:
        timestamp -- The timestamp in milliseconds at which the packet was
                     received (comparable to time.time * 1000)
        router    -- The name of the router that generated this packet
        src       -- The source IP address of the mirrored packet
        dst       -- The destination IP address of the mirrored packet
        ttl       -- The TTL of the mirrored packet
        proto     -- The protocol number of the mirrored packet
        payload   -- The mirrored packet payload (bytestring)"""

    def __init__(self, src, dst, timestamp=None, ttl=0, proto=0, payload=None,
                 router=None):
        """Register the IP addresses and additional fields."""
        self.src = ip_address(unicode(src))
        self.dst = ip_address(unicode(dst))
        self.timestamp = timestamp
        self.ttl = ttl
        self.proto = proto
        self.payload = payload
        self.payload_h = hash(payload)
        self.router = router

    def __len__(self):
        """The size of the mirrored packet."""
        return len(self.payload)

    def __str__(self):
        return ('<Packet :mirrored-by {rid} :from {src} :to {dst} '
                ':proto {proto} :payload-len {len_}>'.format(
                    rid=self.router, src=self.src, dst=self.dst,
                    proto=self.proto, len_=len(self)))

    def __hash__(self):
        return hash((self.src, self.dst, self.proto, self.payload_h))

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            raise NotImplementedError()
        return (self.dst == other.dst and
                self.src == other.src and
                self.proto == other.proto and
                self.payload_h == other.payload_h)

    def __ne__(self, other):
        return not self.__eq__(other)

    @classmethod
    def from_dissector(cls, data, rdict):
        """:param data: The data tuple returned by the dissector
        :param rdict: an IP address to router mapping"""
        try:
            sec, usec, rid, src, dst, ttl, proto, buf = data
        except ValueError as e:
            raise RecvError('Cannot extract data from the dissector! %s' %
                            str(e))
        router_address = ip_address(unicode(rid)).compressed
        try:
            router = rdict(router_address)
        except KeyError:
            raise RecvError('Mirrored packet from unknown source (%s)!' %
                            router_address)
        return cls(src, dst, timestamp=sec * 1000 + usec / 1000,
                   router=router, ttl=ttl, proto=proto, payload=buf)
