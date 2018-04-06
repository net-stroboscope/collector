import py.test

from stroboscope.algorithms.key_points import KPS_OPT


@py.test.mark.parametrize('path, level, expected', [
    (['SEAT', 'SALT', 'KANS', 'CHIC', 'NEWY'], 0, [('SEAT', 4), ('NEWY', 1)]),
    (['SEAT', 'SALT', 'KANS', 'CHIC', 'NEWY'], 1, [('SEAT', 4), ('NEWY', 0)]),
])
def test_abilene(abilene, path, level, expected):
    _test_kp_sampling(abilene, path, level, expected)


@py.test.mark.parametrize('path, level, expected', [
    (('A', 'B', 'C', 'D'), 0, [('A', 1), ('B', 1), ('C', 1), ('D', 1)]),
    (('A', 'B', 'C', 'D'), 1, [('A', 1), ('B', 2), ('D', 0)]),
    (('A', 'L', 'C', 'D'), 1, [('A', 1), ('L', 2), ('D', 0)])
])
def test_paper_graph(paper_graph, path, level, expected):
    _test_kp_sampling(paper_graph, path, level, expected)


def _test_kp_sampling(graph, path, level, expected):
    keypoints = KPS_OPT[level](graph, path)
    assert expected == keypoints
