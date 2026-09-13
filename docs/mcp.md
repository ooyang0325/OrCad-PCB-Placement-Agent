# Portable local MCP interface

`orcad-placement-mcp` and `python -I -m orcad_placement_agent.mcp_server` expose
the same bounded controller through standard **stdio MCP**. No HTTP listener,
cloud service, public endpoint, automatic Cadence startup, or unattended save
is provided.

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
The server has sixteen tools; all reference operations are read-only.

`pcb_plan_placement`, `pcb_prepare_next_placement`, and `pcb_placement_status`
implement the [closed-loop mission workflow](placement-missions.md). They
return actual images and native-derived planning facts, but do not mutate a
board. `pcb_prepare_save`, `pcb_save_revision`, and `pcb_save_status` provide a
separate visually grounded, one-use SAVE approval and outcome-reconciliation
path. Save success is not automatic reopen verification.

## Autonomous placement and approved saves

Portable installs allow bounded placement writes by default. Calling
`pcb_apply_placement` with an exact visually bound proposal autonomously
dispatches it once; no interactive input or server flag is required.

Apply has only `session` and `proposal` as arguments. There is no placement
confirmation, per-call override, or elicitation round trip. The controller
still verifies the proposal, visual binding, session, source board, and fresh
native scene before mutation.

Save remains separate. Only the operator may add `--allow-interactive-writes`,
and only when the client uses genuine interactive input with no automatic
elicitation answers. The flag is not a model tool argument, and no installer or
marketplace manifest enables it. The Save response must exactly match
`SAVE <save-proposal-id>`; decline, cancellation, missing UI support, or a wrong
answer does not save.

The controller consumes a placement dispatch once. A transport retry cannot send a second
placement. Missing post-images preserve the recorded native outcome; use the
bounded recovery tools rather than replaying Apply.

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
