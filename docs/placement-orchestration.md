# PCB placement orchestration

**PCB placement orchestrator** is the supervising agent above the planner,
independent reviewer, and executor. The portable equivalent is the explicitly
invoked `pcb-placement-orchestrate` skill.

It manages an end-to-end placement **workflow**, including the prerequisites
between logical design intake and a fully placed, routing-reviewed layout.
The [executable mission engine](placement-missions.md) now supplies complete
target planning, fresh-readback progress and one-at-a-time native proposal
preparation. The coordinator is not an autorouter or direct execution role.

Select **PCB placement orchestrator** in a client supporting repository agents,
or invoke `pcb-placement-orchestrate` from the installed plugin. Supply the
mission intake below; do not supply a generic "place everything" request without
a verified design inventory. Bundled expertise and full rule lookup need no
textbooks or index. Version 0.5.0 adds experimental managed-board missions;
version 0.9.0 adds separate approved library setup. Upgrade/restart existing
installs deliberately and stage a matching bootstrap to receive the new tools.

Optionally prepare routing-focused context without opening or changing a board:

```powershell
.\.venv\Scripts\python.exe -m orcad_placement_agent agent-context `
    --goal "Coordinate staged placement and identify routing-readiness requirements" `
    --topic placement --topic routing-readiness --topic return-paths
```

The coordinator can retrieve bundled rules directly, or use this packet. A
reference packet alone is not a schematic, a component inventory, or a native
board snapshot.

## Continuous mission driver

In 0.10.0, start **PCB placement orchestrator** with one complete mission request,
the exact attached session, and explicit requirements. The coordinator continues
supported worker handoffs itself; the user need not switch roles, copy proposal
IDs between agents, or say "continue" after every successful step.

`pcb_placement_intake(session)` is read-only. It does not start Cadence, attach
windows, load libraries, prepare placements or save:

| Result | Coordinator action |
|---|---|
| `setup_required` / `library_preparation` | Inspect the returned setup PNG, delegate preparation, independent review and executor LOAD handoff |
| `intake_ready` / `placement_planning` | Inspect the PNG and native inventory, reconcile assembly/DNP and explicit grid/clearance, then plan |
| `blocked` / `reconciliation_required` | Reconcile the exact pending request using its appropriate status tool; do not replay |
| `blocked` / `attachment_required` | Delegate staging/attachment recovery to the executor and resume intake after verification; never pick an unrelated window |
| Other `blocked` results | Keep the native message and phase, delegate in-scope diagnosis/repair and recheck; do not repeat LOAD or remove geometry to evade checks |

Only a definite missing-package rejection routes to a setup inspection. A
timeout, source change, absent PNG, or padstack rejection does not trigger a
different write path. No additional attach is needed on an already-bound session.
After a confirmed `libraries_loaded` outcome, return directly to full intake;
the model may still reject pads, routing or other unsupported features.

Each reviewer/executor calls `pcb_read_proposal(session, proposal, kind)` for
the exact archived preparation PNG and bound data. `kind` is `placement`,
`library`, or `save`; the controller validates that proposal and its binding.
The call issues no native command, creates no approval, and does not make archived
evidence fresh. Workers must actually view the image and separately inspect current
native state. Host image limits or unavailable independent delegation must be
reported; repeated image calls or coordinator self-review do not resolve them.

Continue preparation, independent review, execution and fresh placement-status
readback until all expected parts are actually observed at their target poses.
Real external blockers and explicit prepare-only scope are stop conditions,
not routine "continue" prompts. LOAD/SAVE need no per-operation approval.
This is bounded automation, not a self-modifying controller: unsupported native
features require diagnosed, tested implementation changes and native acceptance.

### Validation recovery

A failed validation does not end the agent's turn or require the user to say
"continue". Give a non-blocking progress update, retain the failing diagnostic,
repair the cause within scope and rerun the focused check. Worker failures go
back to the coordinator as recovery handoffs with evidence and a next action.
The coordinator resumes the mission automatically after checks pass.

Pause only dependent mutations while native state is uncertain. Continue
read-only diagnosis and independent work, reconcile the recorded operation,
then prepare a fresh reviewed proposal when a correction requires one. Never
replay consumed proposals, weaken validation or treat failure as success.
Repeated no-progress attempts require a new approach or internal escalation,
not identical retries or an automatic user interruption. Request user action
only after in-scope recovery is exhausted and intent, target ambiguity, scope
or an external prerequisite genuinely requires it. This is workflow guidance;
native rejection, asset-continuity and replay protections remain enforced.

## Current capability boundary

`pcb_sessions` now returns a `capabilities` declaration alongside the recorded
sessions. It identifies the current backend's supported and unsupported
operations. This is software scope, not proof of a live license or open board.

| Operation | Current backend |
|---|---|
| Inspect the supported board and return PNG/native evidence | Supported after staging/attachment |
| Move/rotate an already-placed original-fixture symbol | Implemented for autonomous exact-proposal dispatch, subject to native gates |
| Import a schematic/netlist or resolve arbitrary libraries | Not implemented |
| Load exact missing package definitions from verified staged files | Separate all-unplaced managed-board-v1 setup binding and autonomous exact-proposal dispatch; non-atomic, in memory only; native acceptance pending |
| Initially place an unplaced logical component | Implemented for explicit managed-board-v1 with embedded simple SMT footprints; native acceptance pending |
| Plan complete target sets and reconcile fresh placement coverage | Implemented, with pin-based routing proxies and explicit constraints |
| Save a new revision through an agent | Separate autonomous exact-proposal SAVE; no implicit reopen |
| Write arbitrary production boards | Not supported |
| Route traces or prove routing feasibility | Not implemented |

Zero physically placed components is supported by the new implementation when
the staged board already contains the logical inventory and embedded geometry.
Check the exact session model: the default fixture model does not gain initial
placement. Missing libraries block full placement inspection until the separate
[library-setup phase](library-loading.md) succeeds. Only known all-unplaced
managed-board-v1 inventory and bounded verified staged PSM/PAD/FSM/SSM files
qualify; unsupported setup, empty logical designs and unsupported topology
remain blockers. LOAD is not import, existing-definition refresh, placement,
Save, persistence or global configuration. Normal `pcb_inspect` still separately
gates complex geometry afterward. Do not bypass blockers with raw commands.
An older server without a declaration is unknown, not implicitly capable.
Native acceptance still requires a dedicated fixture and genuine interactive approval.

## Mission intake

Establish a mission identifier and the exact design/session, or mark it
unbound. Record the operator-supplied source of every required input:

| Input | Why it is needed |
|---|---|
| Schematic/netlist, BOM variant, expected refdes and explicit DNP exclusions | Defines what must be placed; an empty database is not an empty completed design |
| Footprint/padstack and pin/net mappings | Establishes physical parts and electrical connections |
| Outline, origin/units, keepouts, mechanical/fixed interfaces and heights | Establishes legal placement and protected constraints |
| Stackup, reference planes and allowed via technology | Establishes escape and routing choices |
| Critical-net topology, edge rates, timing/length budgets, currents and isolation requirements | Makes routing-aware reasoning design-specific |
| Device layout guidance, thermal, assembly and test requirements | Establishes constraints that geometry alone cannot supply |

Distinguish **no logical design**, **logical design with zero placed symbols**,
**partially placed**, and **already routed/partly routed**. Never invent missing
parts, roles or connectivity. Never discard fixed placements or rip up routing
to manufacture a clean starting state.

## Phases and responsibility

| Phase | Owner and output | Exit gate |
|---|---|---|
| Intake and capability check | Coordinator: inventory, constraints, missing-input/backend queue | Expected assembly and supported operations are explicit |
| Missing-library setup, when required | Operator attaches with `--library-setup`; planner prepares, reviewer checks, executor requests exact LOAD | Actual load outcome reconciled and normal full placement inspection succeeds; no persistence inferred |
| Functional floorplan | Planner: regions, signal/power flow, anchors and alternatives | Reviewer accepts the assumptions for human engineering review |
| Mechanical anchors | Planner/reviewer/executor loop | Exact reviewed poses and fresh native/visual readback |
| Critical groups | Same loop: ICs/converters/clock/RF/analog with their confirmed local passives | Escape and critical loop/return requirements remain feasible |
| Remaining groups | Same loop: dependency-ordered, bounded batches | Reserved routing channels, thermal and assembly access preserved |
| Coverage closure | Coordinator + native evidence | Every expected in-scope refdes is observed placed; no unexplained missing/extra parts |
| Routing-aware closure | Independent reviewer | Each routing gate has evidence or a justified not-applicable result |
| Persistence handoff | Operator via separate approved save workflow | Explicit saved/unsaved state; never infer saving from Apply |

The coordinator delegates only the three named PCB roles. Its `agent`/`todo`
tools support coordination and tracking, not general coding, shell access, or
permission bypass. The three workers retain their bounded scope. All four
agents inspect actual PNGs and reference corresponding native facts. For library setup, use
`pcb_inspect_libraries`, planner `pcb_prepare_library_load`, executor
`pcb_load_libraries` and read-only `pcb_library_load_status`. The coordinator
does not prepare or load directly. A setup image is not full placement evidence.

Serialize native editor access, including overlapping inspections. Offline
analysis can be parallel when it does not compete for the editor. Every worker
gets complete context; do not assume it inherits the coordinator's history.

## Handoff contract

Each work package states:

- Mission and exact session; current phase and backend capability limits.
- Expected/in-scope placed/remaining/excluded inventory and its evidence source.
- Fixed or protected objects, relevant pin/net functions and device constraints.
- The bounded component group and dependency order; exact proposal IDs only
  after the planner has prepared them through a supported tool.
- Snapshot and visual observation IDs, bundled rule IDs, optional actual PDF citations, input paths,
  and unresolved questions.
- Routing constraints and reserved areas, required result format, success
  criteria, and explicit stop conditions.

The planner returns alternatives, targets, rationale and tradeoffs. The
reviewer returns independent findings and missing inputs, not authorization.
The executor autonomously dispatches the exact reviewed proposal and returns
the native result and post-image; it does not invent a replacement pose or
package/file list. A rejected/rolled-back/unknown result never advances the
placed inventory. LOAD success does not advance it either; partial/uncertain
definition loading is not a rolled-back placement transaction.

If the host cannot delegate, use explicit sequential role handoffs and disclose
the lack of independent execution contexts. Do not pretend a skill name is a
callable native subagent type or label self-review as independent review.

## Routing-aware gates

| Gate | Required review |
|---|---|
| Escape/fanout | Pin access, BGA/fine-pitch escape, via technology, layer budget before surrounding placement |
| Corridors/congestion | Reserved channels, bottlenecks, crossing concentration, assembly/access conflicts |
| Critical topology | Device-required topology, differential/matched groups, timing/length feasibility |
| Return paths | Actual reference planes, discontinuities, layer transitions and return continuity |
| Power and sensitive regions | Confirmed switch/current loops, decoupling connections, noisy/sensitive coupling |
| Physical integration | Isolation/keepouts, thermal paths, fabrication, assembly and test access |

Do not defer all small passives: confirmed local bypass and termination parts
belong with their critical groups. A routing bottleneck can require revisiting
placement, but no revision may erase protected constraints or prior approvals.

Use wire-length, crossing and density estimates only as proxies. They cannot
prove detailed routing, impedance, SI/PI, EMI, thermal performance or assembly
success. If a supported trial-routing tool is unavailable, do not invent one.

## Completion and recovery

Maintain separate ledger fields for:

| Field | Rule |
|---|---|
| Placement coverage | Known, nonempty expected inventory; all in-scope parts observed placed |
| Routing review | Each gate reviewed or explicitly justified not-applicable; unknown is not a pass |
| Routing verification | Independent evidence if performed; otherwise `unverified` |
| Native execution | No unresolved/indeterminate requests counted as success |
| Persistence | Saved artifact evidence or an explicit `in memory only` statement |

**Zero expected and zero placed is not completion** when the design has not
been supplied. Planned positions, a successful dispatch, a favorable review,
or an unchanged DRC count are not completion evidence either.

A valid final description may be **fully placed, routing reviewed; routability
unverified**. It must not become **fully routed** or **manufacturing-ready**
without the corresponding independent evidence.

After an uncertain operation, reconcile its exact request/proposal before
continuing. Use `pcb_library_load_status` for an exact LOAD proposal; do not
infer rollback or retry after a partial/uncertain result. A detected cache
change, even transient, or a break in file-lock/cache-monitoring continuity
requires continued diagnosis and documented fresh-staging recovery after
reconciliation, not another mutation in the uncertain session. Preserve that
session's evidence and unrelated unsaved work. Never replay an Apply or LOAD,
clear pending state, substitute a different board to claim completion or change
host permissions. Planning and exact reviewed placement, library LOAD and
revision SAVE dispatch autonomously; none requires a per-operation human prompt.

## Optional original-source navigation

These historical synthesis references are not required at runtime. Use bundled
rules first; these entries only guide optional original-source retrieval:

- `40 PCB Design Tips Every Designer Should Know.pdf`, physical PDF pages 20-21:
  fixed/critical placement priorities and escape planning before surrounding parts.
- `addc6240-6ef2-4c26-aef3-3ad945773b19.pdf`, physical PDF page 78:
  functional floorplanning, early critical passives, routing channels and references.
- `8dff1002-5362-4168-84a6-20e1c4b760cd.pdf`, physical PDF page 151:
  congestion feedback into placement. This is a historical P-CAD source; its
  product commands are not Cadence APIs.

If using original excerpts, retrieve actual context and cite applicable pages.
No textbook, native board, or local evidence artifact is redistributed here.
