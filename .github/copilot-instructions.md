# Copilot instructions

## Repository context

Repository name: `OrCad-PCB-Review-Agent`.

This project is a Windows-only, bounded autonomous PCB placement prototype.
The controller uses Python 3.12+ and a small SKILL adapter targeting classic
OrCAD X / Allegro X PCB Editor 25.1. Follow `docs\milestones.md`; environment
discovery is not proof of licensed live access.

Python code lives in `src\orcad_placement_agent`. Use the repository's `.venv`
interpreter rather than the global Python, which may be a legacy Cadence
dependency. Do not replace Python 2.7 or modify global Cadence settings.

## Making changes

- Inspect the current repository before implementing a change, and follow
  existing conventions as code and configuration are introduced.
- Keep changes focused on the requested task and preserve unrelated work.
- Commit coherent, verified increments regularly. Use Git for development
  history, not manually maintained checksums or a custom versioning system.
  Retain fingerprints only where needed for board-preservation and proposal/state
  preconditions, not as a replacement for commits.
- Use the human user's configured Git identity as the primary author and
  committer. Do not override it with `Copilot App`; resolve a missing identity
  against the user's GitHub account before committing. Do not rewrite
  published commit attribution without explicit approval.
- Clarify requirements before making consequential technology or integration
  choices that are not specified by the task.
- Keep credentials, local configuration, and proprietary PCB design files
  out of version control.
- Keep the supplied `doc` and `pcb_design_book` directories local-only.
  Author project documentation in `docs`; do not redistribute vendor examples
  or libraries.
- Document setup, usage, and relevant external tool requirements when adding
  runnable functionality.

## Validation

- Install the local package with `.venv\Scripts\python.exe -m pip install -e .`.
- Run targeted tests using `.venv\Scripts\python.exe -m unittest`; the full
  small suite uses `-m unittest discover -s tests -v`.
- Add or update relevant tests when changing behavior, using the established
  test framework if one exists.
- Report validation limitations explicitly rather than claiming unrun checks
  succeeded.
- Python tests do not establish native SKILL, licensing, dispatch, DRC, or
  persistence behavior. Those require the dedicated local synthetic fixture.
- Local PDF support is optional: install `.[knowledge]` in `.venv` only when
  extracting PDFs, not for bundled reference tools. The indexer has no model/network calls; excerpts
  read into Copilot are still processed by the configured Copilot service.
- Portable MCP support uses `.[integrations]`. Validate manifests and installed
  assets without changing client settings or Windows execution policy. Package
  tracked source only; never archive the ignored local reference/design folders.
