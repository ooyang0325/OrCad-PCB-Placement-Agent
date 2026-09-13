# Visual autonomous agent placement

The project extension in `.github\extensions\pcb-placement` connects the
Copilot agents to the existing local Python controller. It exposes bounded
operations, not shell access or arbitrary SKILL evaluation.

## Agent roles

| Role | Native capabilities |
|---|---|
| PCB placement orchestrator | Inspect mission/setup state, track phases and delegate the three workers; no direct prepare/apply/load/save authority |
| PCB placement planner | Inspect the bound board or library setup visually and prepare an exact proposal |
| PCB layout reviewer | Independently inspect placement/setup evidence and read recorded execution outcomes |
| PCB placement executor | Provision sessions/fixtures, execute authorized PCB work using typed tools or inspected controller/CLI/raw SKILL paths, and verify native and saved outcomes |

All four profiles include `pcb_inspect` and must examine the returned PNG.
The executor additionally has `execute` and `edit`, plus `agent` restricted to
the planner and reviewer for independent handoffs. The coordinator delegates
and tracks work; it does not execute shell commands or edit designs. Planning
and review retain their read-only design boundaries.

The execution policy authorizes in-scope startup, window selection, bootstrap
loading, library work, raw SKILL and save/reopen without per-operation approval.
A missing editor or saved fixture should trigger executor provisioning using
the original fixture recipe, not an immediate request for a user-supplied board.
Require process/native board identity, recoverable baselines, native checks and
reconciliation of uncertain results. Host permissions and licensing still apply.

MCP and app LOAD/SAVE now dispatch exact proposals without elicitation or mode
gates. The table below describes the implemented typed tools. Older installed
runtimes need updating and restarting; never fabricate human responses or claim
a rejected call succeeded. New mutation paths require native fixture acceptance;
raw SKILL does not inherit typed rollback or replay guarantees.

## Bounded tools

| Tool | Effect |
|---|---|
| `pcb_reference_catalog` | List bundled expertise and stable rule IDs, without books or a board |
| `pcb_reference_search` | Retrieve bounded bundled-rule candidates |
| `pcb_reference_rule` | Read a complete rule with conditions, checks, limits and synthesis provenance |
| `pcb_sessions` | List recorded staged sessions and declared backend scope; neither proves live readiness |
| `pcb_placement_intake` | Read the exact attached managed board and route missing packages to preparation or a supported board to planning; no mutation |
| `pcb_read_proposal` | Return exact placement/library/save proposal data and its archived preparation PNG without native commands |
| `pcb_review_proposal` | Return one fresh PNG and exact target only when its complete native scene equals the prepared proposal; no mutation or approval |
| `pcb_inspect` | Read fresh native state around capture of only the bound Cadence window |
| `pcb_inspection_status` | Report an unresolved read-only snapshot, or reconcile its exact request ID without replay |
| `pcb_inspect_libraries` | Inspect the bound all-unplaced library-setup inventory and actual PNG; not full placement readiness |
| `pcb_prepare_library_load` | Prepare exact missing package definitions from verified staged files with fresh PNG evidence; no loading |
| `pcb_load_libraries` | Autonomously load only the exact reviewed in-memory definitions once |
| `pcb_library_load_status` | Read/reconcile the exact LOAD outcome without replay; full placement inspection remains separate |
| `pcb_plan_placement` | Plan a complete managed-board mission from explicit requirements and native pin/footprint data |
| `pcb_placement_status` | Reconcile fresh native placement coverage and routing screening |
| `pcb_prepare_next_placement` | Prepare one remaining mission target from fresh state and image |
| `pcb_prepare_placement` | Prepare a supported exact pose, including unplaced managed-board components; no mutation |
| `pcb_apply_placement` | Autonomously apply one exact visually bound proposal in memory |
| `pcb_execution_status` | Read or reconcile the result of an already prepared proposal without replaying it |
| `pcb_prepare_save` | Prepare a visually bound new-revision save proposal, without saving |
| `pcb_save_revision` | Autonomously save an exact visually bound proposal as a new managed revision |
| `pcb_save_status` | Read/reconcile the exact Save result without replay; report reopen separately |

Board tools accept a managed session name such as `board-<id>`, never an arbitrary
directory, executable, native command, or output path. The session must already
be staged and attached before using them; the executor may perform that CLI
setup autonomously. Do not choose
an unrelated session just because it appears first in the list.

`pcb_read_proposal` takes `session`, `proposal`, and `kind` (`placement`,
`library`, or `save`). Its `freshness: archived` result is an evidence handoff,
not a current board inspection or authorization. The reviewer and executor can
retrieve it themselves rather than asking the user to provide a filesystem PNG.
An image-rendering failure is still a failed visual checkpoint.

For live exact-proposal review, prefer `pcb_review_proposal` with the same three
arguments. The controller compares the complete fresh native scene and board
identity against the frozen preparation, then returns a single fresh PNG with
`scene_matches_proposal: true`. The reviewer must view its pixels and assess
the exact target; archived-image viewing is not additionally required on this
path. This is not a target preview, execution authorization or proof of DRC.
A changed scene returns `blocked`, not a new proposal or an automatic retry.
The extension worker deadline is 300 seconds for multi-read actions; each
controller round trip remains bounded to 60 seconds.

For typed [library setup](library-loading.md), the executor may attach
with `--library-setup` to a managed-board-v1 session with known nonempty logical
inventory and no placed symbols. Every role examines the actual setup PNG;
the planner or executor prepares the verified staged PSM/PAD/FSM/SSM cache proposal
for independent review, and only the executor performs LOAD. The typed loader does not import logical designs,
refresh existing definitions, place components, save, guarantee persistence or
change global settings. It is non-atomic and can leave a partial or uncertain
outcome. Never infer rollback or replay a LOAD; use `pcb_library_load_status`.
Ordinary `pcb_inspect` must still pass full placement gates afterward, including
the separate unsupported-complex-geometry checks.

Bundled reference tools need no session, index, or local textbooks and do not
open Cadence. They accept only a bounded query or stable card ID, not file paths.
The app interface serves bundled synthesis; optional PDF enrichment remains
available through the portable MCP interface or an explicit CLI context packet.

The binding contains the exact PID, HWND, executable and process creation time.
Recorded titles may retain a startup directory; the native full board path and
session handshake are authoritative. Large Windows process timestamps are
represented as decimal strings across the JavaScript tool boundary to avoid
rounding.

## Visual evidence

An observation contains a PNG, capture metadata, and before/after native
snapshot IDs. The board and modeled scene must remain unchanged during capture.
The capture workflow first requests an acknowledged, board-guarded display-only
fit. This changes viewport framing, not component positions. The native adapter
must be the current staged version; a missing fit receipt is an explicit error.
The image and its metadata are immutable, uniquely named files in the managed
session directory; the tool returns the PNG to the model as an image, not merely
a path or a textual description.

Tool text omits opaque native scene blobs to keep the model context readable.
Use the persisted before/after receipt paths for complete machine-readable
data, rather than treating the abbreviated tool display as a native receipt.

Only the bound Cadence window is eligible. No desktop/screen fallback may
capture unrelated applications. A failed, blank, minimized, unavailable, or
ambiguous capture must be reported rather than replaced with an imagined view.
Framing and visible layers limit what an image shows; a screenshot is not
proof of full geometry coverage, DRC, SI/PI, EMI, thermal, or manufacturing
correctness.

To attach an archived observation to a reference packet:

```powershell
.\.venv\Scripts\python.exe -m orcad_placement_agent agent-context `
    --goal "Review the visible placement and reference evidence" `
    --visual '<managed-session>\visual-<observation-id>.json'
```

The packet links the actual PNG and its matching saved snapshot. It remains
archived evidence; use `pcb_inspect` for current state.

## Dispatch and outcome

The execution tool's model-visible schema contains only session and proposal
identifiers. There is no placement confirmation or approval parameter.

The extension reads the frozen proposal and visual binding, rechecks the exact
refdes/pose/pivot/board, and autonomously dispatches it once. A planner
recommendation alone is not executable: the exact proposal must complete the
independent review handoff and all visual/native checks.
Before LOAD or SAVE, MCP and app tools validate access to the actual proposal
PNG and revalidate the proposal binding. Missing image access blocks dispatch;
successful access is not proof that the agents examined the image. No human
confirmation is requested. Each operation uses its own exact proposal and
single-use dispatch record, not the other operation's request.
If the operator staged with the optional unverified-3D policy, both snapshot
forms disclose the exact unverified names and warnings; LOAD, Apply and SAVE
descriptions retain the warning. Carry it through every review and handoff.
No tool field can toggle this staging policy, and approval does not verify
3D content or mechanical clearance.

The [portable MCP package](installation.md) enables bounded placement writes by
default, including library LOAD and revision SAVE. `--allow-interactive-writes`
is now an ignored compatibility flag; no interactive mode or elicitation is needed.

Before dispatch, the controller consumes the proposal once and the native
adapter rechecks the full scene. An accepted Windows message is not success:
the explicit native receipt determines `applied`, `rejected`, `rolled_back`,
or `indeterminate`. The tool then captures the resulting placement and compares
that observation with the recorded outcome where available.

If the post-image fails after a move, the native outcome still stands. The
tool reports the visual failure without pretending that the move rolled back.
Use `pcb_execution_status`; never resend Apply or create a duplicate proposal
to evade an uncertain result. Saving remains separate through `pcb_prepare_save`
and `pcb_save_revision`, with `pcb_save_status` for recovery. The extension does
not implicitly save or expose an Undo tool.

A post-operation image may time out on its own read-only snapshot after the
placement receipt is already complete. Execution status preserves that receipt
and reports the pending inspection separately. Use `pcb_inspection_status`
first to identify it, then supply that exact request ID to reconcile its late
result. It refuses a pending placement or a different request; it does not
silently clear unrelated state.

The default native write model remains limited to the original synthetic
fixture. Explicit managed-board-v1 adds conditional initial placement and
separate all-unplaced library setup, not arbitrary real-board support.
A board rejected by the selected full placement model does not become editable
merely because its image is visible or library loading succeeded.

Current native evidence establishes window capture, useful fitted framing,
scene correlation, visually grounded proposal preparation, and one-use
autonomous dispatch in the controller. Apply/rollback/Undo/save acceptance must
not be inferred from successful screenshots or fake-backend tests.
Native library-LOAD acceptance is also pending; no successful loading,
partial-failure recovery or persistence is claimed from packaging or mock tests.

## Extension setup and validation

Open this repository in a Copilot host that supports project extensions. The
SDK is supplied by the host; no npm package installation is required. Reload
extensions after changes and ensure `pcb-placement` is ready. A separate
standalone CLI does not automatically provide these app-extension tools.

After upgrading profiles or tools, start a new client session or restart the
client and verify the selected roles' actual allowlists. An extension-only hot
reload may expose new tools without updating pre-existing cached agents. This
occurred with a cached PCB reviewer that still lacked `pcb_inspect_libraries`
and `pcb_library_load_status` despite updated profile source. Reviewing an
archived actual PNG/manifest and reporting that gap does not satisfy a fresh
setup inspection gate.

The reported live LOAD attempt used the genuine human UI directly during
controlled developer acceptance. It was not a completed orchestrator mission
or acceptance of the full three-role live workflow. Its indeterminate native
outcome remains separate from client lifecycle/tool-discovery evidence.

The Python process uses this worktree's `.venv\Scripts\python.exe`. Requests are
JSON on stdin to a fixed module with `shell: false`; responses and images are
bounded. The extension requests no sensitive environment variables or external
model credentials.

Python tests use the existing unittest suite. Extension handler tests can also
run under that suite when `OPA_NODE` identifies an existing Node.js 20+ runtime:

```powershell
$env:OPA_NODE = '<absolute-path-to-node.exe>'
.\.venv\Scripts\python.exe -m unittest tests.test_extension_tools tests.test_agent_actions tests.test_visuals
```

Tests exercise autonomous placement and simulate Save responses only in
isolated fake backends. They do not establish live operations. Native movement,
rollback, Undo and persistence claims still require dedicated live acceptance.

Images returned to Copilot are processed by the configured service/model, just
like reference excerpts. Do not upload them or board files to additional
services. The local runtime and artifacts are not a security boundary against
another malicious process running as the same Windows user.
