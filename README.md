# cjm-notebook-decompose-core

A Jupyter/nbdev notebook decomposition core for context graphs — the **compositor**
that puts notebooks on-graph by reusing the two source-type cores.

A notebook **is a `CodeModule`** whose authored source is an ordered sequence of
**verbatim cells** (the lossless source substrate). The compositor:

- reads the `.ipynb` (stdlib `json`) + parses nbdev `#|` directives;
- emits one verbatim, content-hashed **`Cell`** node per cell (`CONTAINS` from the
  notebook module, `NEXT` chain for order) — outputs are intentionally dropped
  (derived, not source);
- runs **`cjm-python-decompose-core`** over each `#| export` code cell → `CodeSymbol`
  nodes under the notebook module (`DEFINES`), each tagged with its source cell;
- runs **`cjm-markdown-decompose-core`**'s parse over each markdown cell → prose
  title/refs on the cell;
- links the **interleaving**: a markdown cell `DOCUMENTS` the symbols of the code
  cell it precedes (the structure nbdev only has as proximity, made queryable).

Because cells are stored verbatim, the notebook (and its exported `.py`) can be
regenerated faithfully — this is the first concrete step toward **graph-as-source-
of-truth** (notebook → graph as the authoring surface, `.py`/`.ipynb` as
projections). See the [self-hosting graph arc](https://github.com/cj-mills/cjm-substrate).

## Layering

- `read` — schema-free notebook parsing (`json` + `#|` directives).
- `compose` — bind a parsed notebook onto `CodeModule` / `Cell` / `CodeSymbol` nodes
  + edges, reusing the python and markdown cores.
- `ingest` — flatten decomposed notebooks into `(nodes, edges)` wire-dict lists for
  `cjm_context_graph_layer.ops.extend_graph`.

## License

Apache-2.0
