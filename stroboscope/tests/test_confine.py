import py.test

from stroboscope.algorithms.confine import CONFINE_OPT


@py.test.mark.parametrize('region, level, expected', [
    (('SEAT', 'SALT', 'KANS', 'CHIC', 'NEWY'), 0,
     set([('KANS', 'HOUS'), ('CHIC', 'ATLA'), ('CHIC', 'WASH'),
          ('NEWY', 'WASH'), ('SEAT', 'LOSA'), ('SALT', 'LOSA')])),
    (('SEAT', 'SALT', 'KANS', 'CHIC', 'NEWY'), 1,
     set(['HOUS', 'WASH', 'LOSA', 'ATLA'])),
])
def test_abilene(abilene, region, level, expected):
    _test_confine(abilene, region, level, expected)


@py.test.mark.parametrize('region, level, expected', [
    (('A', 'B', 'C', 'D'), 0,
     set([('A', 'L'), ('A', 'F'), ('B', 'K'), ('B', 'J'), ('B', 'H'),
          ('B', 'L'), ('C', 'H'), ('C', 'G'), ('C', 'U'), ('C', 'F'),
          ('C', 'L'), ('D', 'G')])),
    (('A', 'B', 'C', 'D'), 1, set(['K', 'J', 'H', 'G', 'L', 'F', 'U'])),
    (('A', 'B', 'C', 'D'), 2, set(['P', 'H', 'G', 'L', 'F']))
])
def test_paper_graph(paper_graph, region, level, expected):
    _test_confine(paper_graph, region, level, expected)


@py.test.mark.parametrize('level, expected', [
    (0, set([('A', 'A"'), ('B', 'B"'), ('C', 'C"')])),
    (1, set(['A"', 'B"', 'C"'])),
    (2, set(['E', 'F']))
])
def test_dual_egress_gadget(dual_egress_gadget, level, expected):
    _test_confine(dual_egress_gadget, ('A', 'B', 'C'), level, expected)


@py.test.mark.parametrize('level, expected', [
    (0, set([('B', 'D')])),
    (1, set(['D'])),
    (2, set([]))
])
def test_stub_graph_gadget(stub_graph_gadget, level, expected):
    _test_confine(stub_graph_gadget, ('A', 'B', 'C'), level, expected)


def _test_confine(graph, region, level, expected):
    confinement_region = CONFINE_OPT[level](graph, region)
    assert expected == confinement_region
