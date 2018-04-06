/* Compile this through setuptools/distutils, i.e.
 * python setupy.py install
 * You can also activate the debug logs:
 * CFLAGS+=-D_DEBUG pip install ...*/
#include <Python.h>
#include <structmember.h>

#include <sys/socket.h>
#include <unistd.h>
#include <netdb.h>
#include <netinet/ip.h>
#include <netinet/if_ether.h>

#include <stdio.h>

#define DISSECT_RBUF 2048

#ifdef _DEBUG
#define DEBUG(msg, ...)\
	fprintf(stderr, "__dissector_c_ext: " msg "\n", ##__VA_ARGS__)
#else
#define DEBUG(msg, ...) do {} while (0)
#endif
#define GOTO_DEBUG(label, msg, ...)\
	do {\
		DEBUG(msg, ##__VA_ARGS__);\
		goto label;\
	} while (0)

typedef struct {
	uint32_t src;
	uint32_t dst;
	uint8_t proto;
	uint8_t ttl;
	const uint8_t *payload_ptr;
} info_t;

/*
 * Dissect the given packet buffer to extract properties of interest for
 * Stroboscope */
static int dissect_packet(const uint8_t *buf, size_t len, info_t *res)
{
#define ADVANCE(x) do {\
		len -= (x); \
		buf += (x); \
	} while (0)
	/* FIXME XXX TODO
	 * Write a proper dissector:
	 * GRE can have TLVs
	 * https://tools.ietf.org/html/rfc1701
	 * Support ERSPAN types I to III
	 * https://tools.ietf.org/html/draft-foschiano-erspan-01
	 * */
	unsigned int offset;
	uint8_t c, k, s;
	uint16_t encap;
	const struct iphdr *outerip, *innerip;

	if (!res || len < sizeof(*outerip)) {
		GOTO_DEBUG(err, "Packet is too short for IPv4 (%zd bytes)", len);
	}
	outerip = (struct iphdr*)buf;

	if(outerip->protocol != IPPROTO_GRE) {
		GOTO_DEBUG(err, "Packet is not a GRE packet (proto: %u)",
				outerip->protocol);
	}
	if (len < outerip->ihl * 4 + 4) {
		GOTO_DEBUG(err, "Packet is too short to contain a GRE header "
				"(%zd bytes)\n", len);
	}
	ADVANCE(outerip->ihl * 4);

	if (buf[1] & 0x07) {
		GOTO_DEBUG(err, "GRE version is not 0 (but %u)", buf[1] & 0x07);
	}
	encap = ntohs(*((uint16_t*)&buf[2]));
	if (encap != ETHERTYPE_IP) {
		GOTO_DEBUG(err, "Encapsulated packet is not IPv4 (proto: %u)", encap);
	}

	/* Advance past the GRE header */
#define CHECKBIT(v, i) (((v) & (1 << (7 - (i)))) >> (7 - (i)))

	c = CHECKBIT(buf[0], 0);
	k = CHECKBIT(buf[0], 2);
	s = CHECKBIT(buf[0], 3);
	ADVANCE(4);

#undef CHECKBIT

	offset = 4 * c + 4 * k + 4 * s;

	if (len < offset + sizeof(*innerip)) {
		GOTO_DEBUG(err, "Length does not match CKS bits + IP header (c: %u, "
				"k: %u, s:%u) len: %zd < offset: %d + 20",
				c, k, s, len, offset);
	}
	ADVANCE(offset);
	innerip = (struct iphdr*)buf;

	/* Parse the new IPv4 header */
	if (innerip->version != 4) {
		GOTO_DEBUG(err, "Does not support yet non IPv4 packet");
	}
	res->ttl = innerip->ttl;
	res->proto = innerip->protocol;
	res->src = ntohl(innerip->saddr);
	res->dst = ntohl(innerip->daddr);

	if (len < innerip->ihl * 4) {
		GOTO_DEBUG(err, "Encapsulated packet has been cut: %zd vs %d",
				len, innerip->ihl * 4);
	}
	ADVANCE(innerip->ihl * 4);

	res->payload_ptr = len ? buf : NULL;

	return len;

err:
	return -1;
#undef ADVANCE
}


static PyObject *dissectorError;
#define ERROR(x) PyErr_SetString(dissectorError, (x));

typedef struct {
	PyObject_HEAD
		int fd;
	long error_count;
} Dissector;


	static PyObject*
Dissector_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	(void)args; (void)kwds;

	Dissector *self;

	if ((self = (Dissector *)type->tp_alloc(type, 0))) {
		self->fd = -1;
	}

	return (PyObject *)self;
}

PyDoc_STRVAR(class_doc_str,
		"The Dissector class.\nProvides a wrapper around a GRE socket which"
		" provides timestamp of received packets.\n"
		"__init__(sfd) -> The socket file descriptor to operate on.");

	static int
Dissector_init(Dissector *self, PyObject *args, PyObject *kwds)
{
	static char *kwlist[] = {"sfd", NULL};
	int timestampOn = 1;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "i", kwlist, &self->fd)) {
		return -1;
	}

	if (self->fd < 0) {
		ERROR("Invalid socket file descriptor");
		return -1;
	}

	if (setsockopt(self->fd, SOL_SOCKET, SO_TIMESTAMP, (int *)&timestampOn,
				sizeof(timestampOn)) < 0) {
		PyErr_SetFromErrno(PyExc_OSError);
		return -1;
	}

	DEBUG("Created new dissector");

	return 0;
}


PyDoc_STRVAR(dissect_recv_doc,
		"Block until a packet is received.\n"
		":return: (timestamp sec, timestamp usec,\n"
		"          emitting router IP address,\n"
		"          packet source IP, packet destination IP, IP TTL\n"
		"          payload protocol number, payload bytes)");

static PyObject*
dissect_recv(Dissector *self)
{
	/* Properties we want to extract */
	static uint8_t rbuf[DISSECT_RBUF];
	static struct timeval tv = {0, 0};
	static struct sockaddr_in src;
	/* Control message structure */
	static struct iovec iov = {
		.iov_base = rbuf,
		.iov_len = sizeof(rbuf)
	};
	static char ctrl[CMSG_SPACE(sizeof(tv))];
	static struct msghdr msg = {
		.msg_control = ctrl,
		.msg_controllen = sizeof(ctrl),
		.msg_name = &src,
		.msg_namelen = sizeof(src),
		.msg_iov = &iov,
		.msg_iovlen = 1
	};

	struct cmsghdr *cmsg = (struct cmsghdr *)&ctrl;
	int rval, err;
	info_t pkt_info;

	if (self->fd < 0) {
		ERROR("Invalid socket file descriptor");
		return NULL;
	}

	Py_BEGIN_ALLOW_THREADS
		rval = recvmsg(self->fd, &msg, 0);
	if (rval < 0) {
		Py_BLOCK_THREADS
			PyErr_SetFromErrno(PyExc_OSError);
		return NULL;
	}
	DEBUG("Received data: %d", rval);
	if (cmsg->cmsg_level == SOL_SOCKET &&
			cmsg->cmsg_type == SCM_TIMESTAMP &&
			cmsg->cmsg_len == CMSG_LEN(sizeof(tv))) {
		memcpy(&tv, CMSG_DATA(cmsg), sizeof(tv));
	}

	err = dissect_packet(rbuf, rval, &pkt_info);
	Py_END_ALLOW_THREADS
		if (err >= 0)
			return Py_BuildValue("llIIBBis#", tv.tv_sec, tv.tv_usec,
					ntohl(src.sin_addr.s_addr), pkt_info.src, pkt_info.dst,
					pkt_info.ttl, pkt_info.proto, pkt_info.payload_ptr, err);

	++self->error_count;
	Py_RETURN_NONE;
}

PyDoc_STRVAR(errcnt_doc,
		"Return the number of malformed packets that have been discarded by the"
		" dissector");

	static PyObject*
dissector_err_count(Dissector *self)
{
	return PyLong_FromLong(self->error_count);
}

static PyMemberDef Dissector_members[] = {
	/* Sentinel */
	{NULL}
};

static PyMethodDef Dissector_methods[] = {
	{"recv", (PyCFunction)dissect_recv, METH_NOARGS, dissect_recv_doc},
	{"error_count", (PyCFunction)dissector_err_count, METH_NOARGS, errcnt_doc},
	/* Sentinel */
	{NULL}
};

static PyTypeObject dissect_DissectorType = {
	PyObject_HEAD_INIT(NULL)
		0,                         /*ob_size*/
	"stroboscope._dissect.Dissector",             /*tp_name*/
	sizeof(Dissector), /*tp_basicsize*/
	0,                         /*tp_itemsize*/
	0,                         /*tp_dealloc*/
	0,                         /*tp_print*/
	0,                         /*tp_getattr*/
	0,                         /*tp_setattr*/
	0,                         /*tp_compare*/
	0,                         /*tp_repr*/
	0,                         /*tp_as_number*/
	0,                         /*tp_as_sequence*/
	0,                         /*tp_as_mapping*/
	0,                         /*tp_hash */
	0,                         /*tp_call*/
	0,                         /*tp_str*/
	0,                         /*tp_getattro*/
	0,                         /*tp_setattro*/
	0,                         /*tp_as_buffer*/
	Py_TPFLAGS_DEFAULT | Py_TPFLAGS_BASETYPE, /*tp_flags*/
	class_doc_str,             /* tp_doc */
	0,		                   /* tp_traverse */
	0,		                   /* tp_clear */
	0,		                   /* tp_richcompare */
	0,		                   /* tp_weaklistoffset */
	0,		                   /* tp_iter */
	0,		                   /* tp_iternext */
	Dissector_methods,         /* tp_methods */
	Dissector_members,         /* tp_members */
	0,                         /* tp_getset */
	0,                         /* tp_base */
	0,                         /* tp_dict */
	0,                         /* tp_descr_get */
	0,                         /* tp_descr_set */
	0,                         /* tp_dictoffset */
	(initproc)Dissector_init,  /* tp_init */
	0,                         /* tp_alloc */
	Dissector_new,             /* tp_new */
};

static PyMethodDef dissect_methods[] = {
	/* Sentinel */
	{NULL}
};

#ifndef PyMODINIT_FUNC	/* declarations for DLL import/export */
#define PyMODINIT_FUNC void
#endif
	PyMODINIT_FUNC
init_dissect(void)
{
	PyObject* m;

	dissect_DissectorType.tp_new = PyType_GenericNew;
	if (PyType_Ready(&dissect_DissectorType) < 0)
		return;

	if(!(m = Py_InitModule3("stroboscope._dissect", dissect_methods,
					"Dissector low-level module.")))
		return;

	Py_INCREF(&dissect_DissectorType);
	PyModule_AddObject(m, "Dissector", (PyObject *)&dissect_DissectorType);

	dissectorError = PyErr_NewException(
			"stroboscope._dissect.error", NULL, NULL);
	Py_INCREF(dissectorError);
	PyModule_AddObject(m, "error", dissectorError);
}
