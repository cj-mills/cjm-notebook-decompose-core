"""Project a notebook BACK out of the graph (graph -> .ipynb) — the round-trip leg.

The compositor's inverse: regenerate a notebook from its stored VERBATIM `Cell` nodes,
proving the cell substrate is a LOSSLESS source (the make-or-break fidelity primitive of
[[graph-as-source-of-truth-inversion]]). Operates on `CellNode`s OR queried graph wire
dicts (so the regeneration reads the GRAPH, not just the in-memory decomposition — the
real "graph is a sufficient source" proof).

Outputs are NOT restored — they are derived, re-runnable, and were intentionally not
stored; the SOURCE round-trips exactly. From a regenerated notebook, `nbdev-export`
yields the `.py`, so graph -> notebook -> `.py` follows. This is a v1 read-of-the-graph
regeneration; "the graph OWNS formatting" (canonical emit) is the later B step.
"""

import json
from typing import Any, Dict, Iterable, List, Tuple

NBFORMAT = 4
NBFORMAT_MINOR = 5


def _cell_fields(
    node: Any,  # A CellNode or a queried Cell graph node (wire dict)
) -> Tuple[int, str, str, str]:  # (index, cell_type, cell_key, source)
    """Pull (index, cell_type, cell_key, source) from a CellNode or a wire dict."""
    if isinstance(node, dict):
        p = node.get("properties", {})
        return (p.get("index", 0), p.get("cell_type", "raw"),
                p.get("cell_key", ""), p.get("source", ""))
    return (node.index if node.index is not None else 0, node.cell_type,
            node.cell_key, node.source)


def notebook_dict_from_cells(
    cells: Iterable[Any],  # CellNodes or queried Cell wire dicts (any order; sorted by index here)
) -> Dict[str, Any]:  # The reconstructed `.ipynb` JSON structure
    """Rebuild the `.ipynb` JSON from verbatim cells (ordered by index).

    Source is emitted as nbformat line-lists (`splitlines(keepends=True)`) so a join
    reproduces the verbatim text exactly; code cells get empty `outputs` /
    `execution_count` (outputs are derived, not stored)."""
    rows = sorted((_cell_fields(c) for c in cells), key=lambda t: t[0])
    nb_cells: List[Dict[str, Any]] = []
    for _idx, ctype, key, source in rows:
        cell: Dict[str, Any] = {"cell_type": ctype, "id": key, "metadata": {},
                                "source": source.splitlines(keepends=True)}
        if ctype == "code":
            cell["outputs"] = []
            cell["execution_count"] = None
        nb_cells.append(cell)
    return {"cells": nb_cells, "metadata": {},
            "nbformat": NBFORMAT, "nbformat_minor": NBFORMAT_MINOR}


def render_notebook(
    cells: Iterable[Any],  # CellNodes or queried Cell wire dicts
    indent: int = 1,       # JSON indent (nbformat convention is 1)
) -> str:  # The serialized `.ipynb` text
    """Serialize regenerated cells to `.ipynb` JSON text."""
    return json.dumps(notebook_dict_from_cells(cells), indent=indent) + "\n"


def cells_for_module(
    cell_nodes: Iterable[Any],  # Queried Cell wire dicts (e.g. find_nodes_by_label "Cell")
    module_id: str,             # The notebook CodeModule id to filter to
) -> List[Any]:  # The cells belonging to that notebook
    """Filter queried Cell nodes down to one notebook module (by `module_id` property)."""
    out = []
    for n in cell_nodes:
        p = n.get("properties", {}) if isinstance(n, dict) else {}
        if p.get("module_id") == module_id:
            out.append(n)
    return out
