# Portable local MCP interface

`orcad-placement-mcp` and `python -I -m orcad_placement_agent.mcp_server` expose
the same bounded controller through standard **stdio MCP**. No HTTP listener,
cloud service, public endpoint, or automatic Cadence startup is provided.
Exact-proposal LOAD and revision SAVE dispatch autonomously.

Install from the trusted checkout:

```powershell
.\.venv\Scripts\python.exe -m pip install -e ".[integrations]"
.\.venv\Scripts\python.exe -I -X utf8 -m orcad_placement_agent.mcp_server
```

The second command waits for an MCP client; stdout is the protocol. Do not add
banner output to launchers. The optional `integrations` extra uses the official
MCP Python SDK 2.2 series. The underlying controller still supports Windows
classic PCB Editor 25.1. The fixture model remains default; experimental
managed-board-v1 must be explicitly staged and still requires native acceptance.

## Tools

The server exposes `pcb_sessions`, `pcb_inspect`, `pcb_prepare_placement`,
`pcb_apply_placement`, `pcb_execution_status`, and `pcb_inspection_status`.
Inspection/preparation return native PNG image blocks and bounded structured
metadata. Use the saved receipt paths for full native scene data.

`pcb_placement_intake` routes an exact already-attached managed session to
library preparation or placement planning using native state and an actual PNG.
`pcb_read_proposal` returns an exact proposal's archived preparation image with
its validated binding, using `session`, `proposal`, and `kind` (`placement`,
`library`, `save`). Both are read-only and require no elicitation. Neither
silently repairs unsupported geometry or grants LOAD/SAVE authority.

`pcb_reference_catalog`, `pcb_reference_search`, and `pcb_reference_rule` expose
36 bundled original PCB rules immediately, without books, a database, or PDF
dependencies. Search returns stable `card_id` citations; rule lookup returns
applicability, required inputs, checks, tradeoffs, failure modes, limits and
development-time bibliography. It does not claim to read original books at runtime.

Optionally set `--knowledge-db <path>` or `OPA_KNOWLEDGE_DB` to enrich results
with local PDF evidence; no database path is accepted from a model argument.
Bundled matches are in `hits`; optional PDF matches are in `supplement_hits`,
with distinct `source_kind` values. Missing/stale/corrupt supplements produce
warnings without disabling real bundled expertise. `pcb_reference_page` is
strictly for original PDF excerpts and errors when no local index is configured.
Install `.[knowledge]` only when extracting PDFs; catalog notices expose gaps.
The server has twenty-three tools; all reference operations are read-only.

`pcb_review_proposal` returns one fresh native PNG plus an exact prepared target
only when the full scene and board identity still match its preparation.
It accepts `session`, `proposal`, and `kind` (`placement`, `library`, `save`).
This avoids requiring two image downloads for live review; no claim of viewing
an archived image is made. Scene mismatch, missing pixels or invalid bindings
block review rather than dispatching a move.

`pcb_inspect_libraries`, `pcb_prepare_library_load`, `pcb_load_libraries`, and
`pcb_library_load_status` implement separate [library setup](library-loading.md).
The LOAD tool dispatches autonomously after proposal/image validation and does
not place components or save the board.
The operator first uses `attach --library-setup` for explicitly staged,
all-unplaced managed-board-v1 inventory. Preparation is limited to a verified
bounded staged PSM/PAD/FSM/SSM cache. LOAD is non-atomic and in memory only,
with partial/uncertain outcomes possible: it is not import, existing-definition
refresh, placement, Save, persistence or global configuration. Full
`pcb_inspect` is still required afterward and may reject complex geometry.
Native LOAD acceptance is pending.

`pcb_plan_placement`, `pcb_prepare_next_placement`, and `pcb_placement_status`
implement the [closed-loop mission workflow](placement-missions.md). They
return actual images and native-derived planning facts, but do not mutate a
board. `pcb_prepare_save`, `pcb_save_revision`, and `pcb_save_status` provide a
separate visually grounded, one-use SAVE dispatch and outcome-reconciliation
path. Save success is not automatic reopen verification.

## Autonomous writes

Portable installs allow bounded placement writes by default. Calling
`pcb_apply_placement` with an exact visually bound proposal autonomously
dispatches it once; no interactive input or server flag is required.

Apply, LOAD and SAVE each accept only `session` and `proposal`. There is no
confirmation, per-call override, or elicitation round trip. The controller
still verifies the proposal, visual binding, session, source board, and fresh
native scene before mutation.

Library LOAD and revision SAVE remain separate operations, enabled by default
in both legacy and newer MCP protocol modes. No interactive client or
auto-answer hook is needed. `--allow-interactive-writes` and the Python
`allow_interactive_writes` argument are retained as ignored compatibility
options. Restart the MCP server after updating; an older installed runtime can
still prompt until it is replaced. Host tool permissions remain independent.

New operations use `library-dispatch-<id>.json` and `save-dispatch-<id>.json`
records without confirmation text. Old approval records remain readable and
block replay after upgrade. LOAD still pins verified library assets through
native completion; uncertain asset continuity blocks subsequent writes. SAVE
still refuses an existing revision destination and never overwrites the source.

The controller consumes a placement dispatch once. A transport retry cannot send a second
placement. Missing post-images preserve the recorded native outcome; use the
bounded recovery tools rather than replaying Apply, LOAD or SAVE. Reconcile a
partial/uncertain LOAD with `pcb_library_load_status`; do not claim atomic
rollback or retry to recover a missing image.

## Installed packages

Wheels include the original SKILL adapter, probe, synthetic fixture recipe,
and the three original JSON expertise packs.
They do not include vendor libraries, books, PCB binaries, screenshots, or
indexes. Native staging resolves these trusted package assets rather than
looking in the client's arbitrary working directory.

Generated client commands and capture workers use Python isolated mode so
untrusted working-directory modules or `PYTHONPATH` cannot shadow the installed
controller. No global PATH, Python 2.7, Cadence settings or execution policy
changes are required.

Images and excerpts returned over MCP are processed by the selected client
and model. This is local tool execution, not a promise of offline inference.
Native mutation acceptance remains a separate local validation milestone.
