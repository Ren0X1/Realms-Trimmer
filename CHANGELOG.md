# 📜 Changelog

All notable changes to Realms Trimmer are listed here.
Versions use the `vMAJOR.MINOR.PATCH` scheme.

## v1.0.0 — 2026-11-06

- 🆕 Trimmed copy of a world keeping only visited chunks (`InhabitedTime > 0`) plus a configurable margin
- 🆕 Trims `region`, `entities` and `poi` together and deletes region files that end up empty
- 🆕 Supports both the new `dimensions/` layout and the classic `region/`, `DIM-1/`, `DIM1/` one
- 🆕 Window mode (double-click) with input/output folder pickers, plus a CLI with `--margen`, `--nombre` and `--analizar`
- 🆕 Renames the copy in `level.dat` so it's easy to tell apart in the world list
- 🛡️ The original world is never modified; the output folder must not exist and can't be inside the world
- 🧪 Unit tests on a synthetic world and CI on Windows + Linux
