# tex_citations

Extract all citation keys from a LaTeX document **in order of appearance**, following `\input`, `\include` and friends recursively, and write them to a file as a single comma-separated list.

Useful when you need the ordered list of references of a paper (e.g. for a review form, a reference check, or to compare with the `.bib` file).

## Features

- Walks the main file linearly and descends into included files **at the exact point where they occur**, so the order matches the compiled document.
- Supports natbib, biblatex and standard LaTeX cite commands (`\cite`, `\citep`, `\citet`, `\parencite`, `\textcite`, `\autocite`, `\footcite`, `\nocite`, ...), including starred variants and optional arguments (`\cite[p.~3]{key}`).
- Supports biblatex multi-cite commands (`\cites`, `\parencites`, `\textcites`, ...).
- Follows `\input`, `\include`, `\subfile`, `\InputIfFileExists`, plain-TeX `\input file`, and the `import` package (`\import`, `\subimport`, ...).
- Ignores comments (`%`, but not escaped `\%`), `verbatim`/`lstlisting`/`minted`/`comment` environments and `\verb`.
- Removes duplicates (keeps the first occurrence) unless asked otherwise.
- Detects cyclic inputs and reports missing files.
- Pure Python 3, no dependencies.

## Requirements

Python 3.8+.

## Usage

```bash
python tex_citations.py main.tex -o citations.txt
```

Output (`citations.txt`):

```
spong2006robot,siciliano2009robotics,slotine1991applied,...
```

and a short summary on stderr:

```
47 keys (90 occurrences) from 15 file(s) -> citations.txt
```

### Options

| Option | Description |
|---|---|
| `-o`, `--output FILE` | Output file (default: `citations.txt`) |
| `--sep SEP` | Separator between keys (default: `,`) |
| `--keep-duplicates` | Keep every occurrence instead of the first one only |
| `--one-per-line` | Write one key per line instead of a single list |
| `--no-follow` | Do not descend into `\input` / `\include` |
| `--path DIR` | Extra directory to search for input files (repeatable) |
| `--report` | Print `file:line: key` for each citation to stderr |
| `--stdout` | Also print the resulting list to stdout |

### Examples

```bash
# One key per line, printed also to the terminal
python tex_citations.py main.tex --one-per-line --stdout

# Every occurrence, with file and line of each citation
python tex_citations.py main.tex --keep-duplicates --report

# Separator "; " and an extra search path for sections
python tex_citations.py main.tex --sep "; " --path Sections
```

## Limitations

- Citation commands defined through custom macros are not expanded; add their names to `CITE_COMMANDS` in the script if needed.
- Conditional compilation (`\if...`, `\includeonly`) is not evaluated: every included file is scanned.
