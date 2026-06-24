"""Cross-cell method re-attribution (@patch + incremental `Class.method = fn` idioms)."""

import json
import tempfile
from pathlib import Path

from cjm_notebook_decompose_core.compose import decompose_notebook_file
from cjm_notebook_decompose_core.project import render_notebook


def _cell(cid, ctype, source):
    c = {"cell_type": ctype, "id": cid, "metadata": {}, "source": source}
    if ctype == "code":
        c["outputs"], c["execution_count"] = [], None
    return c


def _nb(*cells):
    return {"cells": list(cells), "metadata": {}, "nbformat": 4, "nbformat_minor": 5}


# A class + a @patch method + an incremental-assigned method + a genuinely free fn +
# an UNRECOGNIZED method-shaped fn (self first param, no @patch / assignment).
NB = _nb(
    _cell("c0", "code", ["#| default_exp core\n"]),
    _cell("c1", "code", ["#| export\n", "class Store:\n", "    def __init__(self): self.db = {}\n"]),
    _cell("c2", "code", ["#| export\n", "@patch\n", "def get(self: Store, k):\n", "    return self.db.get(k)\n"]),
    _cell("c3", "code", ["#| export\n", "def put(self, k, v):\n", "    self.db[k] = v\n", "Store.put = put\n"]),
    _cell("c4", "code", ["#| export\n", "def helper(x):\n", "    return x + 1\n"]),
    _cell("c5", "code", ["#| export\n", "def orphan_method(self, y):\n", "    return y\n"]),
)


def _decompose(tmp):
    p = Path(tmp) / "core.ipynb"
    p.write_text(json.dumps(NB, indent=1) + "\n")
    return p, decompose_notebook_file("demo", str(p), tmp, package="demo")


def test_patch_and_assign_methods_reattributed_to_class():
    with tempfile.TemporaryDirectory() as tmp:
        _, d = _decompose(tmp)
        methods = {s.qualname for s in d.symbols if s.symbol_kind == "method"}
        assert "Store.get" in methods and "Store.put" in methods  # both idioms attributed
        patterns = {r["pattern"] for r in d.diagnostics["reattributed"]}
        assert patterns == {"patch", "assign"}
        # the genuinely free function is NOT re-keyed
        free = {s.qualname for s in d.symbols if s.symbol_kind == "function" and "." not in s.qualname}
        assert "helper" in free and "Store.get" not in free


def test_class_defines_the_reattributed_methods():
    with tempfile.TemporaryDirectory() as tmp:
        _, d = _decompose(tmp)
        store = next(s for s in d.symbols if s.qualname == "Store")
        getm = next(s for s in d.symbols if s.qualname == "Store.get")
        defines = {(e["source_id"], e["target_id"]) for e in d.edges if e["relation_type"] == "DEFINES"}
        assert (store.id, getm.id) in defines           # class -> method (not module -> fn)
        module_defines_get = any(e["source_id"] == d.module.id and e["target_id"] == getm.id
                                 for e in d.edges if e["relation_type"] == "DEFINES")
        assert not module_defines_get


def test_unrecognized_method_shaped_is_surfaced_not_reattributed():
    with tempfile.TemporaryDirectory() as tmp:
        _, d = _decompose(tmp)
        unrec = {u["qualname"] for u in d.diagnostics["unrecognized"]}
        assert "orphan_method" in unrec                  # self-first-param, no @patch/assign -> flagged
        assert "helper" not in unrec                     # not method-shaped


def test_reattribution_preserves_verbatim_round_trip():
    with tempfile.TemporaryDirectory() as tmp:
        p, d = _decompose(tmp)
        orig = json.loads(p.read_text())
        regen = json.loads(render_notebook(d.cells))
        def src(c): return "".join(c["source"]) if isinstance(c["source"], list) else c["source"]
        assert [src(c) for c in regen["cells"]] == [src(c) for c in orig["cells"]]


def test_reattributed_method_keeps_cell_key():
    with tempfile.TemporaryDirectory() as tmp:
        _, d = _decompose(tmp)
        getm = next(s for s in d.symbols if s.qualname == "Store.get")
        # the method still knows which cell defined it (DOCUMENTS / conventions rely on this)
        assert getm.properties.get("cell_key") == "c2"
        assert "__first_param__" not in getm.properties   # temp keys stripped
