"""Schema-free Jupyter/nbdev notebook parsing (stdlib `json`).

Reads an `.ipynb` into an ordered list of cells (type, verbatim source, stable key,
nbdev `#|` directives) plus the `#| default_exp` export target. Carries NO graph
dependency — the schema binding lives in `compose`. nbdev directives are parsed with
a thin regex over `#|` lines (no nbdev dependency); swap in nbdev's own parser later
if edge cases demand it.
"""

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

# An nbdev directive line: `#| export`, `#| hide`, `#| default_exp core`, ...
_DIRECTIVE_RE = re.compile(r"^\s*#\|\s*(.+?)\s*$")
_DEFAULT_EXP_RE = re.compile(r"^\s*#\|\s*default_exp\s+(\S+)")
# Directive first-tokens that mark a code cell as part of the exported module.
_EXPORT_DIRECTIVES = {"export", "exporti", "exports"}


@dataclass
class ParsedCell:
    """One notebook cell, parsed but not yet schema-bound."""
    cell_type: str                  # "code" | "markdown" | "raw"
    source: str                     # Verbatim cell source (lossless)
    index: int                      # Positional index in the notebook
    cell_key: str                   # Stable key: nbformat cell `id` if present, else str(index)
    directives: List[str] = field(default_factory=list)  # nbdev `#|` directives (raw text after `#|`)

    @property
    def is_export(self) -> bool:  # Whether this code cell contributes to the exported module
        """True if a code cell carries an `export`/`exporti`/`exports` directive."""
        return self.cell_type == "code" and any(
            d.split(":")[0].split()[0] in _EXPORT_DIRECTIVES for d in self.directives if d.split())


@dataclass
class ParsedNotebook:
    """The structural decomposition of one notebook."""
    cells: List[ParsedCell] = field(default_factory=list)  # Cells in document order
    default_exp: Optional[str] = None  # The `#| default_exp` module target (e.g. "core"), if any


def _source_to_str(
    source,  # nbformat cell source: a list of line strings OR a single string
) -> str:  # The joined verbatim source
    """Join nbformat cell source (list-of-lines or string) into one verbatim string."""
    if isinstance(source, list):
        return "".join(source)
    return source or ""


def parse_directives(
    source: str,  # A code cell's source
) -> List[str]:  # The `#|` directive bodies, in order
    """Extract nbdev `#|` directive bodies (the text after `#|`) from a cell."""
    out: List[str] = []
    for line in source.splitlines():
        m = _DIRECTIVE_RE.match(line)
        if m:
            out.append(m.group(1))
    return out


def parse_notebook(
    text: str,  # Full `.ipynb` file text (JSON)
) -> ParsedNotebook:  # The parsed notebook
    """Parse a notebook's JSON into ordered cells + the `#| default_exp` target.

    Raises `json.JSONDecodeError` on malformed JSON (the caller decides). The cell
    key prefers the nbformat `id` (stable across reorder/insert) and falls back to
    the positional index."""
    nb = json.loads(text)
    cells: List[ParsedCell] = []
    default_exp: Optional[str] = None
    for i, c in enumerate(nb.get("cells", [])):
        src = _source_to_str(c.get("source"))
        ctype = c.get("cell_type", "raw")
        directives = parse_directives(src) if ctype == "code" else []
        if ctype == "code":
            for line in src.splitlines():
                m = _DEFAULT_EXP_RE.match(line)
                if m:
                    default_exp = m.group(1)
        cells.append(ParsedCell(cell_type=ctype, source=src, index=i,
                                cell_key=str(c.get("id") or i), directives=directives))
    return ParsedNotebook(cells=cells, default_exp=default_exp)


def parse_notebook_file(
    path: str,  # Path to the `.ipynb`
) -> ParsedNotebook:  # The parsed notebook
    """Read + parse a notebook file (UTF-8)."""
    return parse_notebook(Path(path).read_text(encoding="utf-8"))
