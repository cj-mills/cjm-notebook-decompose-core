# cjm-notebook-decompose-core

<!-- generated from the context graph by `cjm-context-graph readme` — do not edit by hand; edit the graph (the urge to hand-edit = move it on-graph) -->

A Jupyter/nbdev notebook decomposition core for context graphs: a notebook IS a CodeModule whose authored source is an ordered sequence of VERBATIM cells (the lossless source substrate), composing the python decomposer (code cells -> symbols) and the markdown decomposer (markdown cells -> prose) with interleaving edges. The first step toward graph-as-source-of-truth (notebook -> graph).

## Modules

- **`cjm_notebook_decompose_core.__init__`**
- **`cjm_notebook_decompose_core.compose`** — Compose a parsed notebook onto dev-graph-schema nodes (the compositor).
- **`cjm_notebook_decompose_core.ingest`** — Flatten decomposed notebooks into graph elements (the queue-free half).
- **`cjm_notebook_decompose_core.project`** — Project a notebook BACK out of the graph (graph -> .ipynb) — the round-trip leg.
- **`cjm_notebook_decompose_core.read`** — Schema-free Jupyter/nbdev notebook parsing (stdlib `json`).
- **`tests.test_compose`** — Compositor: read + compose a notebook onto CodeModule/Cell/CodeSymbol nodes + edges.
- **`tests.test_project`** — Round-trip: regenerate a notebook from its verbatim cells (graph/cells -> .ipynb).
- **`tests.test_reattribution`** — Cross-cell method re-attribution (@patch + incremental `Class.method = fn` idioms).
- **`tests_manual.real_notebook`** — Dogfood the compositor on a REAL ecosystem nbdev notebook (against a scratch graph).

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

### `tests.test_compose`

- `test_every_cell_is_verbatim_with_contains_and_next` _function_
- `test_export_cells_yield_symbols_under_the_module` _function_
- `test_ingest_flattens_and_is_idempotent` _function_
- `test_interleaving_markdown_documents_following_code` _function_
- `test_markdown_cell_prose_and_references` _function_
- `test_module_path_for_notebook` _function_
- `test_non_export_code_cells_harvest_call_names` _function_ — A non-export code cell (nbdev's test/example vehicle) gets its bare call names
- `test_non_python_export_cell_keeps_verbatim_cell` _function_
- `test_notebook_is_a_codemodule` _function_
- `test_read_cells_directives_and_default_exp` _function_
- `test_within_notebook_calls_resolve` _function_

### `tests.test_project`

- `test_cells_for_module_filters_by_module` _function_
- `test_outputs_are_not_restored_but_source_is_exact` _function_
- `test_render_from_cellnodes_round_trips_source` _function_
- `test_render_from_graph_wire_dicts` _function_

### `tests.test_reattribution`

- `test_class_defines_the_reattributed_methods` _function_
- `test_patch_and_assign_methods_reattributed_to_class` _function_
- `test_reattributed_method_keeps_cell_key` _function_
- `test_reattribution_preserves_verbatim_round_trip` _function_
- `test_unrecognized_method_shaped_is_surfaced_not_reattributed` _function_

### `tests_manual.real_notebook`

- `main` _function_

## Dependencies

**Depends on:** `cjm-context-graph-projection`, `cjm-dev-graph-schema`, `cjm-markdown-decompose-core`, `cjm-python-decompose-core`
**Used by:** `cjm-context-graph-projection`
