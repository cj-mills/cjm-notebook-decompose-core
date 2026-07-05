"""Compositor: read + compose a notebook onto CodeModule/Cell/CodeSymbol nodes + edges."""

import json

import pytest

from cjm_dev_graph_schema.identity import code_module_node_id, entity_node_id
from cjm_dev_graph_schema.vocab import DevNodeKinds, DevRelations

from cjm_notebook_decompose_core.compose import (decompose_notebook, module_path_for_notebook)
from cjm_notebook_decompose_core.ingest import notebook_graph_elements
from cjm_notebook_decompose_core.read import parse_notebook


def _nb():
    """A small nbdev-style notebook: default_exp, a markdown doc cell, an export def cell,
    a second export cell that calls the first, and a hidden test cell."""
    cells = [
        {"cell_type": "code", "id": "c0", "source": ["#| default_exp core\n"]},
        {"cell_type": "markdown", "id": "c1", "source": ["# Core\n", "\n", "The `alpha` helper. See [[some-note]].\n"]},
        {"cell_type": "code", "id": "c2", "source": ["#| export\n", "def alpha(x):\n", '    "Alpha."\n', "    return x + 1\n"]},
        {"cell_type": "markdown", "id": "c3", "source": ["## Widget\n", "\n", "A widget that uses alpha.\n"]},
        {"cell_type": "code", "id": "c4", "source": ["#| export\n", "class Widget:\n", "    def run(self):\n", "        return alpha(1)\n"]},
        {"cell_type": "code", "id": "c5", "source": ["#| hide\n", "assert alpha(1) == 2\n"]},
    ]
    return json.dumps({"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5})


def _decomposed():
    parsed = parse_notebook(_nb())
    return decompose_notebook("cjm-foo", parsed, "cjm_foo/core.py", "/abs/nbs/00_core.ipynb",
                              "sha256:nb", import_name="cjm_foo.core")


# --- read ---

def test_read_cells_directives_and_default_exp():
    parsed = parse_notebook(_nb())
    assert parsed.default_exp == "core"
    assert [c.cell_type for c in parsed.cells] == ["code", "markdown", "code", "markdown", "code", "code"]
    assert parsed.cells[2].is_export is True       # `#| export`
    assert parsed.cells[5].is_export is False      # `#| hide`
    assert parsed.cells[0].cell_key == "c0"        # nbformat id preferred


def test_module_path_for_notebook():
    assert module_path_for_notebook("/r/nbs/00_core.ipynb", "/r", "core", "cjm_foo") == "cjm_foo/core.py"
    assert module_path_for_notebook("/r/nbs/index.ipynb", "/r", None, "cjm_foo") == "nbs/index.ipynb"


# --- compose: the notebook IS a CodeModule ---

def test_notebook_is_a_codemodule():
    d = _decomposed()
    assert d.module.id == code_module_node_id("cjm-foo", "cjm_foo/core.py")
    assert d.module.to_graph_node()["label"] == DevNodeKinds.CODE_MODULE
    about = [e for e in d.edges if e["relation_type"] == DevRelations.ABOUT]
    assert about[0]["target_id"] == entity_node_id("repo", "cjm-foo")


def test_every_cell_is_verbatim_with_contains_and_next():
    d = _decomposed()
    assert len(d.cells) == 6  # ALL cells captured, incl. the hidden test cell
    # verbatim source is preserved exactly (lossless substrate)
    c2 = next(c for c in d.cells if c.cell_key == "c2")
    assert c2.to_graph_node()["properties"]["source"] == "#| export\ndef alpha(x):\n    \"Alpha.\"\n    return x + 1\n"
    contains = [e for e in d.edges if e["relation_type"] == DevRelations.CONTAINS]
    assert len(contains) == 6 and all(e["source_id"] == d.module.id for e in contains)
    nexts = [e for e in d.edges if e["relation_type"] == "NEXT"]
    assert len(nexts) == 5  # a linear spine over 6 cells


def test_export_cells_yield_symbols_under_the_module():
    d = _decomposed()
    quals = {s.qualname for s in d.symbols}
    assert quals == {"alpha", "Widget", "Widget.run"}        # hidden test cell contributes none
    defines = [e for e in d.edges if e["relation_type"] == DevRelations.DEFINES]
    sym = {s.qualname: s.id for s in d.symbols}
    pairs = {(e["source_id"], e["target_id"]) for e in defines}
    assert (d.module.id, sym["alpha"]) in pairs
    assert (sym["Widget"], sym["Widget.run"]) in pairs       # nested DEFINES
    # each symbol is tagged with its source cell (provenance + interleaving)
    assert next(s for s in d.symbols if s.qualname == "alpha").properties["cell_key"] == "c2"


def test_interleaving_markdown_documents_following_code():
    d = _decomposed()
    docs = [e for e in d.edges if e["relation_type"] == DevRelations.DOCUMENTS]
    sym = {s.qualname: s.id for s in d.symbols}
    pairs = {(e["source_id"], e["target_id"]) for e in docs}
    md_widget = next(c for c in d.cells if c.cell_key == "c3")
    md_core = next(c for c in d.cells if c.cell_key == "c1")
    assert (md_core.id, sym["alpha"]) in pairs          # "# Core" cell documents alpha
    assert (md_widget.id, sym["Widget"]) in pairs       # "## Widget" cell documents Widget


def test_markdown_cell_prose_and_references():
    d = _decomposed()
    c1 = next(c for c in d.cells if c.cell_key == "c1")
    assert c1.title == "Core"
    refs = [e for e in d.edges if e["relation_type"] == DevRelations.REFERENCES and e["source_id"] == c1.id]
    assert len(refs) == 1  # [[some-note]] -> a REFERENCES edge


def test_within_notebook_calls_resolve():
    d = _decomposed()
    calls = [e for e in d.edges if e["relation_type"] == DevRelations.CALLS]
    sym = {s.qualname: s.id for s in d.symbols}
    # Widget.run calls alpha (same notebook) -> resolves by unambiguous name
    assert (sym["Widget.run"], sym["alpha"]) in {(e["source_id"], e["target_id"]) for e in calls}


def test_ingest_flattens_and_is_idempotent():
    d = _decomposed()
    n1, e1 = notebook_graph_elements([d])
    # 1 module + 6 cells + 3 symbols = 10 nodes
    assert len(n1) == 10
    n2, e2 = notebook_graph_elements([_decomposed()])
    assert {n["id"] for n in n1} == {n["id"] for n in n2}
    assert {e["id"] for e in e1} == {e["id"] for e in e2}


def test_non_python_export_cell_keeps_verbatim_cell():
    # an export cell that isn't valid Python (a magic) must not crash; cell still captured
    cells = [
        {"cell_type": "code", "id": "c0", "source": "#| default_exp core\n"},
        {"cell_type": "code", "id": "c1", "source": "#| export\n%timeit foo()\n"},
    ]
    parsed = parse_notebook(json.dumps({"cells": cells, "nbformat": 4, "nbformat_minor": 5}))
    d = decompose_notebook("cjm-foo", parsed, "cjm_foo/core.py", "/x.ipynb", "sha256:nb")
    assert len(d.cells) == 2 and d.symbols == []  # no symbols, but verbatim cells survive


def test_non_export_code_cells_harvest_call_names():
    """A non-export code cell (nbdev's test/example vehicle) gets its bare call names
    stashed on the CellNode — the TESTS-edge substrate; export/markdown cells do not."""
    import json

    from cjm_notebook_decompose_core.compose import decompose_notebook
    from cjm_notebook_decompose_core.read import parse_notebook

    nb = json.dumps({"cells": [
        {"cell_type": "code", "id": "c0", "source": "#| default_exp core\n"},
        {"cell_type": "code", "id": "c1",
         "source": "#| export\ndef alpha(x):\n    return x + 1\n"},
        {"cell_type": "code", "id": "c2", "source": "assert alpha(1) == 2\nprint(alpha(3))\n"},
        {"cell_type": "code", "id": "c3", "source": "%magic  # unparseable\n(\n"},
        {"cell_type": "markdown", "id": "c4", "source": "# alpha() prose\n"},
    ], "metadata": {}, "nbformat": 4, "nbformat_minor": 5})
    parsed = parse_notebook(nb)
    dn = decompose_notebook("demo", parsed, "demo/core.py", "/tmp/nb.ipynb", "h")
    by_key = {c.cell_key: c for c in dn.cells}
    assert sorted(by_key["c2"].calls) == ["alpha", "print"]  # dedup (walk order, not source order)
    assert by_key["c3"].calls == []                   # unparseable -> no harvest
    assert by_key["c1"].calls == [] and by_key["c4"].calls == []
    assert sorted(by_key["c2"].to_graph_node()["properties"]["calls"]) == ["alpha", "print"]
