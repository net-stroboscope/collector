import pytest

from stroboscope.network_database import NetDB


@pytest.mark.parametrize('path, expect', [
    (['A'], [['A']]),
    (['A', 'B'], [['A', 'B']]),
    (['A', 'B', 'C'], [['A', 'B', 'C']]),
    (['A', '->', 'C'], [['A', 'B', 'C'], ['A', 'L', 'C'], ['A', 'F', 'C']]),
    (['->', 'D'], [['E2', 'I', 'H', 'C', 'D'],
                   ['E1', 'P', 'J', 'H', 'C', 'D'],
                   ['E1', 'P', 'J', 'B', 'C', 'D'],
                   ['E1', 'P', 'K', 'B', 'C', 'D'],
                   ['E3', 'F', 'C', 'D']])
])
def test_arrow_path_paper(paper_graph, path, expect):
    db = NetDB()
    db.graph = paper_graph
    resolved = db.resolve_region(path)
    assert len(resolved) == len(expect)
    for p in resolved:
        for e in expect:
            if p == e:
                break
        assert p == e
