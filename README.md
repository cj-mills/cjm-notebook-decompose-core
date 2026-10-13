# cjm-notebook-decompose-core

<!-- generated from the context graph by `cjm-context-graph readme` — do not edit by hand; edit the graph (the urge to hand-edit = move it on-graph) -->

A Jupyter/nbdev notebook decomposition core for context graphs: a notebook IS a CodeModule whose authored source is an ordered sequence of VERBATIM cells (the lossless source substrate), composing the python decomposer (code cells -> symbols) and the markdown decomposer (markdown cells -> prose) with interleaving edges. The first step toward graph-as-source-of-truth (notebook -> graph).

## Modules

- **`cjm_notebook_decompose_core.__init__`**
- **`cjm_notebook_decompose_core.compose`** — Compose a parsed notebook onto dev-graph-schema nodes (the compositor).
- **`cjm_notebook_decompose_core.ingest`** — Flatten decomposed notebooks into graph elements (the queue-free half).
- **`cjm_notebook_decompose_core.project`** — Project a notebook BACK out of the graph (graph -> .ipynb) — the round-trip leg.
- **`cjm_notebook_decompose_core.read`** — Schema-free Jupyter/nbdev notebook parsing (stdlib `json`).

## API

### `cjm_notebook_decompose_core.compose`

- `DecomposedNotebook` _class_ — A notebook bound to schema nodes: the module + verbatim cells + code symbols + edges.
- `decompose_notebook` _function_ — Bind a parsed notebook onto a notebook `CodeModule` + verbatim cells + symbols + edges.
- `decompose_notebook_file` _function_ — Read + decompose a notebook file (module path from `default_exp`/package, else the path).
- `module_path_for_notebook` _function_ — Pick the notebook module path: the export target when known, else the `.ipynb` path.

### `cjm_notebook_decompose_core.ingest`

- `notebook_graph_elements` _function_ — Collect decomposed notebooks into the node + edge wire-dict lists for `extend_graph`.

### `cjm_notebook_decompose_core.project`

- `cells_for_module` _function_ — Filter queried Cell nodes down to one notebook module (by `module_id` property).
- `notebook_dict_from_cells` _function_ — Rebuild the `.ipynb` JSON from verbatim cells (ordered by index).
- `render_notebook` _function_ — Serialize regenerated cells to `.ipynb` JSON text.

### `cjm_notebook_decompose_core.read`

- `ParsedCell` _class_ — One notebook cell, parsed but not yet schema-bound.
- `ParsedNotebook` _class_ — The structural decomposition of one notebook.
- `parse_directives` _function_ — Extract nbdev `#|` directive bodies (the text after `#|`) from a cell.
- `parse_notebook` _function_ — Parse a notebook's JSON into ordered cells + the `#| default_exp` target.
- `parse_notebook_file` _function_ — Read + parse a notebook file (UTF-8).

## Dependencies

**Depends on:** `cjm-context-graph-layer`, `cjm-context-graph-primitives`, `cjm-dev-graph-schema`, `cjm-markdown-decompose-core`, `cjm-python-decompose-core`
**Used by:** `cjm-context-graph-projection`
