"""Round-trip: regenerate a notebook from its verbatim cells (graph/cells -> .ipynb)."""

import json

from cjm_notebook_decompose_core.compose import decompose_notebook
from cjm_notebook_decompose_core.project import (cells_for_module, notebook_dict_from_cells,
                                                 render_notebook)
from cjm_notebook_decompose_core.read import parse_notebook


def _nb_text():
    cells = [
        {"cell_type": "code", "id": "c0", "source": "#| default_exp core\n"},
        {"cell_type": "markdown", "id": "c1", "source": "# Core\n\nThe `alpha` helper.\n"},
        {"cell_type": "code", "id": "c2", "source": "#| export\ndef alpha(x):\n    return x + 1\n"},
        {"cell_type": "code", "id": "c3", "source": "#| hide\nassert alpha(1) == 2\n"},
    ]
    return json.dumps({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5})


def test_render_from_cellnodes_round_trips_source():
    text = _nb_text()
    d = decompose_notebook("cjm-foo", parse_notebook(text), "cjm_foo/core.py",
                           "/x.ipynb", "sha256:nb")
    regenerated = render_notebook(d.cells)
    # original cells == regenerated cells, by (type, key, source) — the lossless claim.
    orig = parse_notebook(text).cells
    back = parse_notebook(regenerated).cells
    assert [(c.cell_type, c.cell_key, c.source) for c in orig] \
        == [(c.cell_type, c.cell_key, c.source) for c in back]


def test_render_from_graph_wire_dicts():
    # The Cell wire dicts (what the graph stores) regenerate identically.
    d = decompose_notebook("cjm-foo", parse_notebook(_nb_text()), "cjm_foo/core.py",
                           "/x.ipynb", "sha256:nb")
    wire = [c.to_graph_node() for c in d.cells]
    only = cells_for_module(wire, d.module.id)
    assert len(only) == len(d.cells)
    back = parse_notebook(render_notebook(only)).cells
    assert [c.source for c in back] == [c.source for c in d.cells]


def test_outputs_are_not_restored_but_source_is_exact():
    d = decompose_notebook("cjm-foo", parse_notebook(_nb_text()), "cjm_foo/core.py",
                           "/x.ipynb", "sha256:nb")
    nb = notebook_dict_from_cells(d.cells)
    code = [c for c in nb["cells"] if c["cell_type"] == "code"]
    assert all(c["outputs"] == [] and c["execution_count"] is None for c in code)  # outputs dropped
    # source lines re-join to the exact verbatim text
    export = next(c for c in nb["cells"] if c["id"] == "c2")
    assert "".join(export["source"]) == "#| export\ndef alpha(x):\n    return x + 1\n"


def test_cells_for_module_filters_by_module():
    d = decompose_notebook("cjm-foo", parse_notebook(_nb_text()), "cjm_foo/core.py",
                           "/x.ipynb", "sha256:nb")
    wire = [c.to_graph_node() for c in d.cells]
    assert cells_for_module(wire, "some-other-module") == []
