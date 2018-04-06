import pytest

import stroboscope.network_database as ndb


@pytest.fixture(scope='module')
def abilene():
    return _build_graph(
        routers=('SEAT', 'LOSA', 'SALT', 'HOUS', 'KANS', 'CHIC', 'ATLA',
                 'WASH', 'NEWY'),
        edges=(('SEAT', 'LOSA'), ('SEAT', 'SALT'), ('LOSA', 'SALT'),
               ('LOSA', 'HOUS'), ('SALT', 'KANS'), ('KANS', 'HOUS'),
               ('KANS', 'CHIC'), ('HOUS', 'ATLA'), ('CHIC', 'ATLA'),
               ('CHIC', 'WASH'), ('CHIC', 'NEWY'), ('ATLA', 'WASH'),
               ('WASH', 'NEWY')))


@pytest.fixture(scope='module')
def paper_graph():
    return _paper_graph()

def _paper_graph():
    return _build_graph(
        routers=('A', 'B', 'C', 'D', 'F', 'H', 'I', 'J', 'K', 'L', 'P', 'U'),
        egresses=('E1', 'E2', 'E3'),
        edges=(('A', 'B'), ('A', 'L'), ('A', 'F'), ('I', 'E2'),
               ('B', 'K'), ('B', 'J'), ('B', 'H'), ('B', 'C'), ('B', 'L'),
               ('C', 'H'), ('C', 'D'), ('C', 'U'), ('C', 'F'), ('C', 'L'),
               ('L', 'F'), ('F', 'U'), ('F', 'E3'), ('K', 'P'), ('J', 'P'),
               ('J', 'H'), ('H', 'I'), ('P', 'E1'), ('P', 'E2'), ('E2', 'I')))


@pytest.fixture(scope='module')
def dual_egress_gadget():
    return _build_graph(
        routers=('A', 'B', 'C', 'A"', 'B"', 'C"', 'E', 'F'),
        egresses=('E1', 'E2'),
        edges=(('A', 'B'), ('B', 'C'), ('A"', 'A'), ('A"', 'E'), ('B"', 'B'),
               ('B"', 'E'), ('B"', 'F'), ('C"', 'C'), ('C"', 'F'), ('F', 'E1'),
               ('E', 'E2')))


@pytest.fixture(scope='module')
def stub_graph_gadget():
    return _build_graph(
        routers=('A', 'B', 'C', 'D', 'E', 'F', 'G'),
        edges=(('A', 'B'), ('B', 'C'), ('B', 'D'), ('D', 'E'), ('E', 'F'),
               ('F', 'G'), ('G', 'D')))


def _build_graph(routers=tuple(), egresses=tuple(), edges=tuple()):
    g = ndb.NetGraph()
    for r in routers:
        g.register_router(r)
    for e in egresses:
        g.register_egress(e)
    for u, v in edges:
        g.register_link(u, v)
    g.build_spt()
    return g
