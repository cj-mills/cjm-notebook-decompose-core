"""Compose a parsed notebook onto dev-graph-schema nodes (the compositor).

A notebook IS a `CodeModule` whose authored source is an ordered sequence of
verbatim `Cell`s. This module reuses the two source-type cores rather than
reimplementing them:

- code `#| export` cells -> `cjm_python_decompose_core.parse` -> `CodeSymbol`s under
  the notebook module (DEFINES), each tagged with its source cell;
- markdown cells -> `cjm_markdown_decompose_core.parse` (its general parse layer; the
  memory-specific binding in that core's `extract` is deliberately NOT used) -> a
  prose title + `[[wiki-link]]` references on the cell;
- every cell -> a verbatim, content-hashed `Cell` node (CONTAINS + a NEXT spine);
- the interleaving -> a markdown cell `DOCUMENTS` the symbols of the code cell it
  precedes.

Within-notebook CALLS are resolved by unambiguous bare name (precision over recall);
cross-notebook / notebook->.py call resolution is left to a later corpus pass.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cjm_context_graph_layer.grammar import make_edge
from cjm_context_graph_primitives.provenance import SourceRef
from cjm_dev_graph_schema.nodes import CellNode, CodeModuleNode, CodeSymbolNode
from cjm_dev_graph_schema.vocab import DevRelations
from cjm_markdown_decompose_core.parse import parse_markdown
from cjm_python_decompose_core.parse import monkeypatch_assignments, parse_module

from .read import ParsedNotebook, parse_notebook_file

_METHOD_SELF = {"self", "cls"}  # first-param names that mark a method-shaped function


@dataclass
class DecomposedNotebook:
    """A notebook bound to schema nodes: the module + verbatim cells + code symbols + edges."""
    module: CodeModuleNode               # The notebook AS a CodeModule
    cells: List[CellNode] = field(default_factory=list)        # Verbatim cell nodes, in order
    symbols: List[CodeSymbolNode] = field(default_factory=list)  # Code symbols from the export cells
    edges: List[Dict[str, Any]] = field(default_factory=list)  # CONTAINS/NEXT/DEFINES/DOCUMENTS/CALLS/REFERENCES/ABOUT
    diagnostics: Dict[str, Any] = field(default_factory=dict)  # Method re-attribution outcomes + unrecognized method-shaped fns


def _md_title(parsed) -> Tuple[str, str]:
    """(title, description) for a markdown cell: first heading (else first line) + a snippet."""
    title = parsed.headings[0][1] if parsed.headings else ""
    snippet = ""
    for line in parsed.body.splitlines():
        s = line.strip().lstrip("#").strip()
        if s:
            if not title:
                title = s[:80]
            snippet = s[:200]
            break
    return title, snippet


def _cell_symbols(
    module: CodeModuleNode,  # The notebook module
    cell_source: str,        # The export cell's source
    cell_key: str,           # The cell's stable key (tagged onto each symbol)
    content_hash: str,       # The cell's content hash
    path: str,               # The notebook path (provenance)
) -> Tuple[List[CodeSymbolNode], List[Dict[str, Any]], List[str], List[str]]:
    """Parse one export cell -> (symbols, DEFINES edges, this cell's top-symbol ids, imports).

    Returns ([],[],[],[]) when the cell is not parseable as Python (a partial snippet
    or a magic) — the verbatim cell is still kept by the caller."""
    try:
        parsed = parse_module(cell_source)
    except SyntaxError:
        return [], [], [], []
    symbols: List[CodeSymbolNode] = []
    edges: List[Dict[str, Any]] = []

    def make(ps) -> CodeSymbolNode:
        props: Dict[str, Any] = {"cell_key": cell_key}
        if ps.decorators:
            props["decorators"] = list(ps.decorators)
        # Stash the first-param shape (TEMP keys, popped by the re-attribution pass) so a
        # top-level @patch/incremental method can be re-attributed to its class across cells.
        if ps.kind == "function":
            props["__first_param__"] = ps.first_param
            props["__first_param_annotation__"] = ps.first_param_annotation
        node = CodeSymbolNode(module_id=module.id, qualname=ps.qualname, symbol_kind=ps.kind,
                              path=path, content_hash=content_hash, docstring=ps.docstring,
                              calls=list(ps.calls), refs=list(ps.refs), properties=props)
        symbols.append(node)
        children = [make(c) for c in ps.children]
        if children:
            edges.extend(node.defines_edges([c.id for c in children]))
        return node

    tops = [make(ps) for ps in parsed.symbols]
    edges[:0] = module.defines_edges([t.id for t in tops])
    return symbols, edges, [t.id for t in tops], list(parsed.imports)


def _reattribute_methods(
    module: CodeModuleNode,             # The notebook module
    symbols: List[CodeSymbolNode],      # All decomposed symbols (across cells)
    edges: List[Dict[str, Any]],        # The DEFINES/REFERENCES edges built so far
    mp_assigns: List[Any],              # (class, attr, func) monkey-patch assignments across the notebook
) -> Tuple[List[CodeSymbolNode], List[Dict[str, Any]], Dict[str, str], Dict[str, Any]]:
    """Rebuild the TRUE class->method structure for cross-cell method-splitting idioms.

    nbdev libs split a class across cells to dodge whole-cell rewrites, via `@patch`
    (`def get(self: Store)`) or incremental assignment (`Store.get = get`). The AST walk
    sees those as FREE FUNCTIONS, so the class looks empty. This pass re-keys each such
    function to its real `Class.method` identity (kind=method), converts the module->fn
    DEFINES into class->method DEFINES, and remaps every edge referencing it. The verbatim
    cells are untouched (round-trip/authoring preserved) — only the symbol overlay is fixed.

    Returns (new_symbols, new_edges, id_remap, diagnostics). Diagnostics surface the
    re-attributions AND method-shaped (`self`/`cls` first param) functions it could NOT
    attribute — the lookout for OTHER cross-cell scars beyond these two."""
    class_by_name = {s.qualname: s for s in symbols
                     if s.symbol_kind == "class" and "." not in s.qualname}
    mp = {}  # func name -> (class, attr); first assignment wins
    for cls, attr, func in mp_assigns:
        mp.setdefault(func, (cls, attr))

    id_remap: Dict[str, str] = {}
    owner_of: Dict[str, str] = {}  # new method id -> owning class id (to fix DEFINES source)
    new_symbols: List[CodeSymbolNode] = []
    reattributed: List[Dict[str, str]] = []
    unrecognized: List[Dict[str, Any]] = []

    for s in symbols:
        fp = s.properties.pop("__first_param__", "")
        fpa = s.properties.pop("__first_param_annotation__", "")
        if not (s.symbol_kind == "function" and "." not in s.qualname):
            new_symbols.append(s)
            continue
        decos = s.properties.get("decorators", [])
        owner = method = pattern = None
        if "patch" in decos and fpa in class_by_name:       # Pattern A: @patch + self:Class
            owner, method, pattern = class_by_name[fpa], s.qualname, "patch"
        elif s.qualname in mp and mp[s.qualname][0] in class_by_name:  # Pattern B: Class.m = fn
            cls, attr = mp[s.qualname]
            owner, method, pattern = class_by_name[cls], attr, "assign"
        if owner is not None:
            new = CodeSymbolNode(module_id=module.id, qualname=f"{owner.qualname}.{method}",
                                 symbol_kind="method", path=s.path, content_hash=s.content_hash,
                                 docstring=s.docstring, calls=list(s.calls), refs=list(s.refs),
                                 properties=dict(s.properties))
            id_remap[s.id] = new.id
            owner_of[new.id] = owner.id
            reattributed.append({"from": s.qualname, "to": new.qualname, "pattern": pattern})
            new_symbols.append(new)
        else:
            if fp in _METHOD_SELF:  # method-shaped but unattributed -> a possible OTHER scar
                unrecognized.append({"qualname": s.qualname, "cell_key": s.properties.get("cell_key")})
            new_symbols.append(s)

    if not id_remap:
        return symbols, edges, {}, {"reattributed": [], "unrecognized": unrecognized}

    new_edges: List[Dict[str, Any]] = []
    for e in edges:
        src, tgt, rel = e["source_id"], e["target_id"], e["relation_type"]
        ns, nt = id_remap.get(src, src), id_remap.get(tgt, tgt)
        if rel == DevRelations.DEFINES and src == module.id and tgt in id_remap:
            ns = owner_of[id_remap[tgt]]  # module->fn becomes owning class->method
        new_edges.append(make_edge(ns, nt, rel))
    return new_symbols, new_edges, id_remap, {"reattributed": reattributed, "unrecognized": unrecognized}


def decompose_notebook(
    repo_key: str,            # The repo's durable conceptual slug (the federation anchor)
    parsed_nb: ParsedNotebook,  # The parsed notebook
    module_path: str,         # The notebook module's repo-relative path (export target or the .ipynb path)
    notebook_path: str,       # The `.ipynb` file path (provenance locator)
    nb_content_hash: str,     # Content hash over the notebook file
    import_name: Optional[str] = None,  # Override the dotted import name
) -> DecomposedNotebook:  # The decomposed notebook
    """Bind a parsed notebook onto a notebook `CodeModule` + verbatim cells + symbols + edges."""
    all_imports: List[str] = []
    pending_symbols: List[CodeSymbolNode] = []
    pending_edges: List[Dict[str, Any]] = []
    cells: List[CellNode] = []
    mp_assigns: List[Any] = []  # cross-cell `Class.method = fn` incremental-class assignments
    # tops_by_index: cell index -> its top-symbol ids (for DOCUMENTS interleaving)
    tops_by_index: Dict[int, List[str]] = {}

    # Provisional module (id is stable from repo_key+module_path); imports/docstring filled below.
    module = CodeModuleNode(repo_key=repo_key, module_path=module_path, path=notebook_path,
                            content_hash=nb_content_hash,
                            import_name=import_name, docstring="")

    for cell in parsed_nb.cells:
        ch = SourceRef.compute_hash(cell.source.encode("utf-8"))
        node = CellNode(module_id=module.id, cell_key=cell.cell_key, cell_type=cell.cell_type,
                        source=cell.source, content_hash=ch, index=cell.index,
                        path=notebook_path, directives=list(cell.directives))
        if cell.cell_type == "markdown":
            title, desc = _md_title(parse_markdown(cell.source))
            node.title, node.description = title, desc
            refs = parse_markdown(cell.source).wiki_links
            if refs:
                pending_edges.extend(node.reference_edges(refs))
        elif cell.is_export:
            syms, defs, tops, imps = _cell_symbols(module, cell.source, cell.cell_key, ch, notebook_path)
            pending_symbols.extend(syms)
            pending_edges.extend(defs)
            tops_by_index[cell.index] = tops
            all_imports.extend(imps)
            mp_assigns.extend(monkeypatch_assignments(cell.source))
        cells.append(node)

    # Finalize the module with the union of export-cell imports (dedup, order-preserved).
    seen: Dict[str, None] = {}
    for imp in all_imports:
        seen.setdefault(imp, None)
    module.imports = list(seen)

    # Re-attribute cross-cell @patch / incremental methods to their TRUE class (before the
    # DOCUMENTS/CALLS passes, which key off symbol ids); remap the DOCUMENTS source ids.
    pending_symbols, pending_edges, id_remap, diagnostics = _reattribute_methods(
        module, pending_symbols, pending_edges, mp_assigns)
    if id_remap:
        tops_by_index = {i: [id_remap.get(t, t) for t in tops] for i, tops in tops_by_index.items()}

    edges: List[Dict[str, Any]] = [module.about_edge()]
    edges.extend(pending_edges)

    # CONTAINS (module -> each cell) + the NEXT spine over cells in order.
    for i, c in enumerate(cells):
        edges.append(c.contains_edge())
        if i + 1 < len(cells):
            edges.append(c.next_edge(cells[i + 1].id))

    # DOCUMENTS: a markdown cell documents the symbols defined in the cells that FOLLOW
    # it up to the next markdown cell (the literate-programming "section" it heads) —
    # robust to intervening setup/test cells between the prose and the def it documents.
    for i, c in enumerate(cells):
        if c.cell_type != "markdown":
            continue
        span_tops: List[str] = []
        for nxt in cells[i + 1:]:
            if nxt.cell_type == "markdown":
                break
            span_tops.extend(tops_by_index.get(nxt.index, []))
        if span_tops:
            edges.extend(c.documents_edges(span_tops))

    # Within-notebook CALLS + USES by unambiguous bare name (precision over recall).
    name_to_ids: Dict[str, set] = {}
    for s in pending_symbols:
        name_to_ids.setdefault(s.qualname.split(".")[-1], set()).add(s.id)
    call_map = {n: next(iter(ids)) for n, ids in name_to_ids.items() if len(ids) == 1}
    for s in pending_symbols:
        edges.extend(s.calls_edges(call_map))
        edges.extend(s.uses_edges(call_map))

    return DecomposedNotebook(module=module, cells=cells, symbols=pending_symbols, edges=edges,
                              diagnostics=diagnostics)


def module_path_for_notebook(
    notebook_path: str,          # The `.ipynb` path
    repo_root: str,              # Repo root (for the fallback relative path)
    default_exp: Optional[str],  # The notebook's `#| default_exp` target (or None)
    package: Optional[str] = None,  # The importable package name (e.g. "cjm_foo")
) -> str:  # The notebook module's repo-relative path
    """Pick the notebook module path: the export target when known, else the `.ipynb` path.

    An exporting notebook (`default_exp` + a known package) maps to its EXPORTED module
    path (`pkg/sub/mod.py`) so the notebook and its generated `.py` share one module
    identity (two projections of one module). A non-exporting notebook (e.g. index) keeps
    its repo-relative `.ipynb` path as a doc-notebook container."""
    if default_exp and package:
        return f"{package}/" + default_exp.replace(".", "/") + ".py"
    p = Path(notebook_path)
    try:
        return p.relative_to(repo_root).as_posix()
    except ValueError:
        return p.name


def decompose_notebook_file(
    repo_key: str,                  # The repo's durable conceptual slug
    path: str,                      # Path to the `.ipynb`
    repo_root: str,                 # Repo root (for the fallback module path)
    package: Optional[str] = None,  # Importable package name (for export-target module paths)
) -> DecomposedNotebook:  # The decomposed notebook
    """Read + decompose a notebook file (module path from `default_exp`/package, else the path)."""
    raw = Path(path).read_bytes()
    parsed = parse_notebook_file(path)
    module_path = module_path_for_notebook(path, repo_root, parsed.default_exp, package)
    import_name = module_path[:-3].replace("/", ".") if module_path.endswith(".py") else None
    return decompose_notebook(repo_key, parsed, module_path, str(path),
                              SourceRef.compute_hash(raw), import_name=import_name)
