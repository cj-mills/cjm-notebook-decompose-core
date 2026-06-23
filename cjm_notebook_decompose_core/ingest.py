"""Flatten decomposed notebooks into graph elements (the queue-free half).

Turns `DecomposedNotebook`s into the `(nodes, edges)` wire-dict lists that
`cjm_context_graph_layer.ops.extend_graph` commits: one notebook `CodeModule` + its
verbatim `Cell` nodes + the export-cell `CodeSymbol`s, plus the CONTAINS/NEXT/DEFINES/
DOCUMENTS/CALLS/REFERENCES/ABOUT edges built in `compose`. Deterministic ids make it
idempotent under `extend_graph`. The queue/capability wiring is the driver's concern.
"""

from typing import Any, Dict, Iterable, List, Tuple

from .compose import DecomposedNotebook


def notebook_graph_elements(
    decomposed: Iterable[DecomposedNotebook],  # The decomposed notebooks
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:  # (node wire dicts, edge wire dicts)
    """Collect decomposed notebooks into the node + edge wire-dict lists for `extend_graph`.

    Nodes: one notebook `CodeModule` + its `Cell`s + its `CodeSymbol`s per notebook.
    Edges: the per-notebook edges assembled in `compose`. Re-ingesting the same
    notebooks collides into verified no-ops (deterministic ids)."""
    nodes: List[Dict[str, Any]] = []
    edges: List[Dict[str, Any]] = []
    for d in decomposed:
        nodes.append(d.module.to_graph_node())
        nodes.extend(c.to_graph_node() for c in d.cells)
        nodes.extend(s.to_graph_node() for s in d.symbols)
        edges.extend(d.edges)
    return nodes, edges
