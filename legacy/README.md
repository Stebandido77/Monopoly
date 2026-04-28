# Legacy notebooks

This directory holds the notebooks that started the project. They are
preserved as a historical record of the point of departure — not as
working code.

## Contents

| File | Role |
|---|---|
| `Monopoly.ipynb` | First end-to-end Monopoly simulation. Heuristic strategies, no abstraction layer. |
| `Monopoly_V2.ipynb` | Second pass: more strategies, partial refactor, several documented bugs (see `docs/legacy_bugs.md`). |
| `Modelos_de_optimizacion_estocastico.ipynb` | Initial exploration of MILP / stochastic-programming approaches that motivated the project. |

## Why these are not "the code"

The package under `src/monopoly/` is a clean-slate rewrite, **not a
refactor** of these notebooks. The rewrite reads the official Hasbro
rules as its source of truth and reimplements every mechanic against
that — the legacy code was used only to identify which heuristics were
worth carrying over conceptually. Where the new code disagrees with a
notebook, the new code wins (see the project-level `CLAUDE.md`, "Fuente
de verdad de reglas").

## Excluded from CI

These notebooks are excluded from:

- **`ruff`** — see the `[tool.ruff] exclude` entry in `pyproject.toml`
  (`legacy/`, `*.ipynb`). The notebooks contain hundreds of style
  violations that would never be cleaned up because the files are
  frozen.
- **`pytest`** — `[tool.pytest.ini_options] testpaths = ["tests"]`,
  which never reaches this directory.
- **The build** — `[tool.setuptools.packages.find] where = ["src"]`,
  which only collects modules under `src/`.

If you want to actually *run* the notebooks (e.g. to compare a result
against the rewrite), open them in Jupyter directly. They were last
known to execute against the dependency versions pinned in
`pyproject.toml` plus `matplotlib` and `seaborn` (not pulled in by the
package because the rewrite does not need them).
