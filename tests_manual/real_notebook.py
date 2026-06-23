#!/usr/bin/env python
"""Dogfood the compositor on a REAL ecosystem nbdev notebook (against a scratch graph).

Proves the first graph-as-source-of-truth increment end-to-end on real input:
  1. The notebook is decomposed as a CodeModule with verbatim Cell substrate.
  2. LOSSLESS: the concatenated verbatim cell sources == the notebook's own cell
     sources (no cell content dropped) — the round-trip substrate is faithful.
  3. Export cells yield CodeSymbols under the notebook module; markdown + code cells
     CO-RESIDE; markdown cells DOCUMENT the code they precede (interleaving).
  4. It ingests into a real graph (extend_graph) and the new node/edge kinds land.

Run in the core env with the substrate runtime + the new libs installed -e:

    conda run -n cjm-transcript-correction-core --no-capture-output python \
        cjm-notebook-decompose-core/tests_manual/real_notebook.py
"""
import argparse
import asyncio
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from cjm_context_graph_layer.ops import extend_graph
from cjm_dev_graph_schema.vocab import DevNodeKinds, DevRelations

from cjm_notebook_decompose_core.compose import decompose_notebook_file
from cjm_notebook_decompose_core.ingest import notebook_graph_elements
from cjm_notebook_decompose_core.read import parse_notebook, parse_notebook_file

REPOS = "/mnt/SN850X_8TB_EXT4/Projects/GitHub/cj-mills"
DEFAULT_NB = f"{REPOS}/cjm-forced-alignment-adapter-interface/nbs/core.ipynb"


def _check(label, ok):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}")
    return ok


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--notebook", default=DEFAULT_NB)
    ap.add_argument("--repo", default="cjm-forced-alignment-adapter-interface")
    args = ap.parse_args()

    repo_dir = str(Path(args.notebook).parents[1])  # .../<repo>/nbs/x.ipynb -> <repo>
    package = Path(repo_dir).name.replace("-", "_")
    d = decompose_notebook_file(args.repo, args.notebook, repo_dir, package=package)

    print(f"notebook: {Path(args.notebook).name}  ->  module {d.module.module_path}")
    print(f"  cells={len(d.cells)}  symbols={len(d.symbols)}  edges={len(d.edges)}")
    print(f"  edge kinds: {dict(Counter(e['relation_type'] for e in d.edges))}")

    ok = True
    ok &= _check("notebook is a CodeModule", d.module.to_graph_node()["label"] == DevNodeKinds.CODE_MODULE)

    # LOSSLESS: concatenated verbatim cell sources == the notebook's own cell sources.
    parsed = parse_notebook_file(args.notebook)
    ok &= _check("verbatim cell substrate is lossless (concat == source)",
                 [c.source for c in d.cells] == [c.source for c in parsed.cells])

    ok &= _check("export cells yield CodeSymbols", len(d.symbols) > 0)
    ok &= _check("markdown + code cells co-reside",
                 {c.cell_type for c in d.cells} >= {"code", "markdown"})
    ok &= _check("CONTAINS + NEXT spine present",
                 sum(e["relation_type"] == DevRelations.CONTAINS for e in d.edges) == len(d.cells)
                 and sum(e["relation_type"] == "NEXT" for e in d.edges) == max(len(d.cells) - 1, 0))
    ok &= _check("DOCUMENTS interleaving present",
                 any(e["relation_type"] == DevRelations.DOCUMENTS for e in d.edges))

    # Ingest into a real (scratch) graph, then ROUND-TRIP back out of the graph.
    from cjm_context_graph_projection.factlayer import load_label
    from cjm_context_graph_projection.runtime import open_graph
    from cjm_notebook_decompose_core.project import cells_for_module, render_notebook
    nodes, edges = notebook_graph_elements([d])
    with tempfile.TemporaryDirectory() as tmp:
        db = str(Path(tmp) / "nb.db")
        async with open_graph(db) as gx:
            res = await extend_graph(gx.queue, gx.graph_id, nodes, edges)
            print(f"  ingested: {res.nodes_added} nodes / {res.edges_added} edges")
            ok &= _check("ingest committed Cell + CodeSymbol nodes",
                         res.nodes_added >= len(d.cells) + len(d.symbols))

            # Read the Cell nodes back FROM THE GRAPH and regenerate the notebook.
            cell_nodes = cells_for_module(await load_label(gx, "Cell"), d.module.id)
            regenerated = render_notebook(cell_nodes)
            orig_cells = parsed.cells
            back_cells = parse_notebook(regenerated).cells
            ok &= _check("graph -> notebook round-trips SOURCE losslessly (from the graph)",
                         [(c.cell_type, c.source) for c in orig_cells]
                         == [(c.cell_type, c.source) for c in back_cells])

    print("\nRESULT:", "ALL PASS" if ok else "FAILURES")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
