#!/usr/bin/env python3
"""Extract citation keys from a LaTeX document, in order of appearance.

The scanner walks the main file linearly and descends into \\input, \\include
(and friends) at the exact point where they occur, so the resulting key
sequence matches the order of the compiled document. The keys are written to a
file as a single comma-separated list.

Example:
    python tex_citations.py main.tex -o citations.txt
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Command tables
# ---------------------------------------------------------------------------

# Commands whose (last) mandatory argument is a comma-separated list of keys.
CITE_COMMANDS = {
    # natbib / standard LaTeX
    "cite", "citep", "citet", "citealp", "citealt", "citeauthor",
    "citeyear", "citeyearpar", "citenum", "citetext", "nocite",
    "Citep", "Citet", "Citealp", "Citealt", "Citeauthor",
    "citefullauthor", "shortcite", "citeA", "citeNP",
    # biblatex
    "parencite", "Parencite", "textcite", "Textcite", "autocite", "Autocite",
    "footcite", "footcitetext", "smartcite", "Smartcite", "supercite",
    "fullcite", "footfullcite", "citeauthor*", "citetitle", "citedate",
    "citeurl", "volcite", "Volcite", "pnotecite", "fnotecite",
    # revtex / misc
    "onlinecite", "citenumber", "cref@cite",
}

# biblatex multi-cite commands: an arbitrary number of {..} groups follows.
MULTICITE_COMMANDS = {
    "cites", "Cites", "parencites", "Parencites", "textcites", "Textcites",
    "autocites", "Autocites", "footcites", "smartcites", "supercites",
}

# \cmd{file}
INPUT_COMMANDS = {"input", "include", "subfile", "subfileinclude", "InputIfFileExists"}

# \cmd{dir}{file}  (import package)
IMPORT_COMMANDS = {
    "import", "subimport", "inputfrom", "subinputfrom",
    "includefrom", "subincludefrom",
}

VERBATIM_ENVS = ("verbatim", "lstlisting", "minted", "comment", "Verbatim", "alltt")

TOKEN_RE = re.compile(r"\\([A-Za-z@]+)\*?")
VERBATIM_RE = re.compile(
    r"\\begin\{(" + "|".join(VERBATIM_ENVS) + r")\*?\}.*?\\end\{\1\*?\}",
    re.DOTALL,
)
VERB_RE = re.compile(r"\\verb\*?(?P<d>[^A-Za-z\s])(?P<body>.*?)(?P=d)")

SUFFIXES_TO_TRY = (".tex", ".ltx", ".tikz", ".pgf")


# ---------------------------------------------------------------------------
# Pre-processing
# ---------------------------------------------------------------------------

def strip_comments(text: str) -> str:
    """Remove LaTeX comments while preserving line structure.

    A '%' starts a comment only when it is not escaped, i.e. when the number of
    backslashes immediately before it is even.
    """
    out = []
    for line in text.split("\n"):
        i = 0
        while True:
            j = line.find("%", i)
            if j == -1:
                out.append(line)
                break
            backslashes = 0
            k = j - 1
            while k >= 0 and line[k] == "\\":
                backslashes += 1
                k -= 1
            if backslashes % 2 == 0:
                out.append(line[:j])
                break
            i = j + 1
    return "\n".join(out)


def blank_out(match: re.Match) -> str:
    """Replace a match with as many newlines as it contained (keeps line numbers)."""
    return "\n" * match.group(0).count("\n")


def preprocess(text: str) -> str:
    text = VERBATIM_RE.sub(blank_out, text)
    text = VERB_RE.sub(blank_out, text)
    text = strip_comments(text)
    return text


def read_text(path: Path) -> str:
    data = path.read_bytes()
    for encoding in ("utf-8", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


# ---------------------------------------------------------------------------
# Argument parsing helpers
# ---------------------------------------------------------------------------

def skip_spaces(text: str, i: int) -> int:
    while i < len(text) and text[i] in " \t\r\n":
        i += 1
    return i


def read_group(text: str, i: int, opener: str = "{", closer: str = "}"):
    """Read a balanced group starting at or after position `i`.

    Returns (content, index_after_group) or (None, i) if no group is there.
    """
    j = skip_spaces(text, i)
    if j >= len(text) or text[j] != opener:
        return None, i
    depth = 0
    k = j
    while k < len(text):
        c = text[k]
        if c == "\\":
            k += 2
            continue
        if c == opener:
            depth += 1
        elif c == closer:
            depth -= 1
            if depth == 0:
                return text[j + 1:k], k + 1
        k += 1
    return None, i  # unbalanced


def skip_optional(text: str, i: int) -> int:
    """Skip any number of consecutive [..] optional arguments."""
    while True:
        content, j = read_group(text, i, "[", "]")
        if content is None:
            return i
        i = j


def read_bare_filename(text: str, i: int):
    """Handle plain-TeX style `\\input file.tex` (no braces)."""
    j = skip_spaces(text, i)
    k = j
    while k < len(text) and text[k] not in " \t\r\n{}%\\$&#^_~":
        k += 1
    if k == j:
        return None, i
    return text[j:k], k


def split_keys(raw: str):
    for key in raw.split(","):
        key = key.strip()
        key = " ".join(key.split())
        if key and key != "*":
            yield key


# ---------------------------------------------------------------------------
# File resolution
# ---------------------------------------------------------------------------

def resolve_path(name: str, current_dir: Path, root_dir: Path, extra_dirs) -> Path | None:
    name = name.strip().replace("\\space", " ").strip()
    if not name:
        return None
    # TeX accepts forward slashes on every platform.
    rel = Path(name.replace("\\", "/"))
    if rel.is_absolute():
        candidates = [rel]
    else:
        search_dirs = [current_dir, root_dir, *extra_dirs]
        seen_dirs, dirs = set(), []
        for d in search_dirs:
            d = d.resolve()
            if d not in seen_dirs:
                seen_dirs.add(d)
                dirs.append(d)
        candidates = [d / rel for d in dirs]

    for cand in candidates:
        if cand.is_file():
            return cand
        for suffix in SUFFIXES_TO_TRY:
            with_suffix = cand.with_name(cand.name + suffix)
            if with_suffix.is_file():
                return with_suffix
    return None


# ---------------------------------------------------------------------------
# Core scanner
# ---------------------------------------------------------------------------

class Extractor:
    def __init__(self, root: Path, follow: bool = True, extra_dirs=()):
        self.root = root.resolve()
        self.root_dir = self.root.parent
        self.follow = follow
        self.extra_dirs = [Path(d).resolve() for d in extra_dirs]
        self.citations = []          # list of (key, file, line)
        self.visited_files = []      # files actually parsed, in order
        self.missing = []            # (name, referenced_from)
        self._stack = []             # for cycle detection

    def run(self):
        self._parse(self.root)
        return self.citations

    def _parse(self, path: Path):
        path = path.resolve()
        if path in self._stack:
            print(f"warning: cyclic input ignored: {path}", file=sys.stderr)
            return
        self._stack.append(path)
        self.visited_files.append(path)
        try:
            text = preprocess(read_text(path))
        except OSError as exc:
            print(f"warning: cannot read {path}: {exc}", file=sys.stderr)
            self._stack.pop()
            return

        line_starts = [0]
        for m in re.finditer("\n", text):
            line_starts.append(m.end())

        def line_of(offset: int) -> int:
            lo, hi = 0, len(line_starts) - 1
            while lo < hi:
                mid = (lo + hi + 1) // 2
                if line_starts[mid] <= offset:
                    lo = mid
                else:
                    hi = mid - 1
            return lo + 1

        pos = 0
        while True:
            m = TOKEN_RE.search(text, pos)
            if m is None:
                break
            name = m.group(1)
            pos = m.end()

            if name in CITE_COMMANDS:
                i = skip_optional(text, pos)
                group, j = read_group(text, i)
                if group is None:
                    continue
                for key in split_keys(group):
                    self.citations.append((key, path, line_of(m.start())))
                pos = j

            elif name in MULTICITE_COMMANDS:
                i = pos
                while True:
                    i2 = skip_optional(text, i)
                    group, j = read_group(text, i2)
                    if group is None:
                        break
                    for key in split_keys(group):
                        self.citations.append((key, path, line_of(m.start())))
                    i = j
                pos = i

            elif name in INPUT_COMMANDS:
                group, j = read_group(text, pos)
                if group is None:
                    group, j = read_bare_filename(text, pos)
                if group is None:
                    continue
                pos = j
                self._descend(group, path)

            elif name in IMPORT_COMMANDS:
                d_group, j = read_group(text, pos)
                f_group, k = read_group(text, j) if d_group is not None else (None, j)
                if d_group is None or f_group is None:
                    continue
                pos = k
                self._descend(f_group, path, subdir=d_group)

        self._stack.pop()

    def _descend(self, name: str, parent: Path, subdir: str | None = None):
        if not self.follow:
            return
        current_dir = parent.parent
        if subdir:
            sub = Path(subdir.strip().replace("\\", "/"))
            current_dir = sub if sub.is_absolute() else (current_dir / sub)
        target = resolve_path(name, current_dir, self.root_dir, self.extra_dirs)
        if target is None:
            self.missing.append((name, parent))
            print(f"warning: file not found: {name!r} (from {parent})", file=sys.stderr)
            return
        self._parse(target)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        description="Extract citation keys from a LaTeX document, in order of "
                    "appearance, following \\input and \\include recursively.",
    )
    ap.add_argument("texfile", type=Path, help="main .tex file")
    ap.add_argument("-o", "--output", type=Path, default=Path("citations.txt"),
                    help="output file (default: citations.txt)")
    ap.add_argument("--sep", default=",",
                    help="separator between keys (default: ',')")
    ap.add_argument("--keep-duplicates", action="store_true",
                    help="keep every occurrence instead of first occurrence only")
    ap.add_argument("--one-per-line", action="store_true",
                    help="write one key per line instead of a single list")
    ap.add_argument("--no-follow", action="store_true",
                    help="do not descend into \\input / \\include")
    ap.add_argument("--path", action="append", default=[], metavar="DIR",
                    help="extra directory to search for input files (repeatable)")
    ap.add_argument("--report", action="store_true",
                    help="print file and line for each key to stderr")
    ap.add_argument("--stdout", action="store_true",
                    help="also print the resulting list to stdout")
    args = ap.parse_args(argv)

    if not args.texfile.is_file():
        print(f"error: no such file: {args.texfile}", file=sys.stderr)
        return 1

    extractor = Extractor(args.texfile, follow=not args.no_follow, extra_dirs=args.path)
    citations = extractor.run()

    if args.keep_duplicates:
        keys = [c[0] for c in citations]
    else:
        seen, keys = set(), []
        for key, _, _ in citations:
            if key not in seen:
                seen.add(key)
                keys.append(key)

    text = "\n".join(keys) if args.one_per_line else args.sep.join(keys)
    args.output.write_text(text + "\n", encoding="utf-8")

    if args.report:
        for key, path, line in citations:
            print(f"{path}:{line}: {key}", file=sys.stderr)

    print(
        f"{len(keys)} keys ({len(citations)} occurrences) from "
        f"{len(extractor.visited_files)} file(s) -> {args.output}",
        file=sys.stderr,
    )
    if args.stdout:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
