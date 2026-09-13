// Model-visible actions contain no shell strings, paths, or confirmation answers.
const sessionProperty = {
    type: "string",
    pattern: "^board-[A-Za-z0-9_-]{1,64}$",
    description: "Exact managed board-session name from the supplied context or session list.",
};
const proposalProperty = {
    type: "string",
    pattern: "^[0-9a-f]{64}$",
    description: "Exact visually grounded proposal identifier returned by prepare.",
};

function schema(properties, required = Object.keys(properties)) {
    return { type: "object", properties, required, additionalProperties: false };
}

function requireFields(args, fields) {
    if (!args || typeof args !== "object" || Array.isArray(args) ||
        Object.keys(args).length !== fields.length ||
        fields.some((field) => typeof args[field] !== "string")) {
        throw new Error("Unexpected or missing tool fields.");
    }
    if (fields.includes("session") && !/^board-[A-Za-z0-9_-]{1,64}$/.test(args.session)) {
        throw new Error("Expected a managed session name, not a path.");
    }
    if (fields.includes("proposal") && !/^[0-9a-f]{64}$/.test(args.proposal)) {
        throw new Error("Expected the exact proposal identifier.");
    }
}

export function createPlacementTools({ run, imageResult }) {
    function display(value) {
        return JSON.stringify(value, (key, item) => {
            if (key === "records" && Array.isArray(item)) {
                return item.map(row => Array.isArray(row) && row.length === 3 &&
                    ["scene-part", "policy-part"].includes(row[0])
                    ? [row[0], row[1], "Opaque native data omitted; use the persisted receipt."]
                    : row);
            }
            if (typeof item === "string" &&
                (item.startsWith("OPA-FIXTURE-1;") || item.startsWith("OPA-BOARD-1;"))) {
                return {
                    opaque_scene_omitted_from_display: true,
                    instruction: "Use the persisted native receipt for complete machine-readable scene data.",
                };
            }
            return item;
        });
    }

    async function render(value) {
        let resultType = ["error", "indeterminate", "blocked", "inspection_pending", "library_partial"].includes(value.status) ||
            value.visual_error ? "failure" :
            ["rejected", "rolled_back"].includes(value.status) ? "rejected" : "success";
        const result = { textResultForLlm: display(value), resultType };
        if (value.visual) {
            try {
                result.binaryResultsForLlm = [await imageResult(value.visual)];
            } catch (error) {
                result.resultType = "failure";
                result.textResultForLlm = display({
                    ...value, image_error: error.message,
                    warning: "The native outcome above still stands. Do not repeat LOAD, Apply or Save because its image is unavailable.",
                });
            }
        }
        return result;
    }

    function tool(name, description, parameters, action, fields) {
        return {
            name, description, parameters,
            handler: async (args) => {
                try {
                    requireFields(args, fields);
                    return await render(await run({ action, ...args }));
                } catch (error) {
                    return { resultType: "failure", textResultForLlm: JSON.stringify({
                        status: "error", error: error.message, retry_placement: false,
                    }) };
                }
            },
        };
    }

    const tools = [
        tool("pcb_reference_catalog",
            "List bundled original PCB expertise and stable rule IDs. No books, index, network, or board session required.",
            schema({}), "reference-catalog", []),
        tool("pcb_reference_search",
            "Search bundled PCB guidance. Retrieve full rules by card_id before applying principles to a design.",
            schema({ query: { type: "string", minLength: 1, maxLength: 500 } }),
            "reference-search", ["query"]),
        tool("pcb_reference_rule",
            "Read complete bundled guidance: applicability, required inputs, checks, tradeoffs, limits, and development-time source provenance. Not a runtime book read.",
            schema({ card_id: { type: "string", pattern: "^[a-z][a-z0-9]*(?:-[a-z0-9]+)*$", maxLength: 64 } }),
            "reference-rule", ["card_id"]),
        tool("pcb_sessions",
            "List recorded managed PCB sessions and declared backend capabilities. Neither proves live readiness; do not select an unrelated session.",
            schema({}), "sessions", []),
        tool("pcb_placement_intake",
            "Inspect one exact attached managed session and route missing packages to library preparation or a supported board to planning. Returns a PNG on successful inspection; no loading, placement or approval.",
            schema({ session: sessionProperty }), "intake", ["session"]),
        tool("pcb_read_proposal",
            "Read an exact placement, library or save proposal and its archived preparation PNG without native commands. Examine the actual image; fresh inspection and independent review remain separate.",
            schema({
                session: sessionProperty, proposal: proposalProperty,
                kind: { type: "string", enum: ["placement", "library", "save"] },
            }), "read-proposal", ["session", "proposal", "kind"]),
        tool("pcb_review_proposal",
            "Return one fresh PNG and exact proposal data only when the native scene still equals the prepared scene. Independent visual review is required; no placement, loading, saving or approval.",
            schema({
                session: sessionProperty, proposal: proposalProperty,
                kind: { type: "string", enum: ["placement", "library", "save"] },
            }), "review-proposal", ["session", "proposal", "kind"]),
        tool("pcb_plan_placement",
            "Plan all required components from a fresh managed-board-v1 native inventory, explicit design requirements JSON, and actual PNG. Requires expected_refdes, clearance_mm and grid_mm; does not apply or approve.",
            schema({
                session: sessionProperty,
                requirements_json: { type: "string", minLength: 2, maxLength: 131072 },
            }), "mission-plan", ["session", "requirements_json"]),
        tool("pcb_placement_status",
            "Inspect fresh native placement coverage and routing screening for the exact stored mission, without editing.",
            schema({ session: sessionProperty, mission: { type: "string", pattern: "^[0-9a-f]{32}$" } }),
            "mission-status", ["session", "mission"]),
        tool("pcb_prepare_next_placement",
            "Prepare the next unplaced mission component using fresh state and an actual PNG for autonomous dispatch.",
            schema({ session: sessionProperty, mission: { type: "string", pattern: "^[0-9a-f]{32}$" } }),
            "mission-next", ["session", "mission"]),
        tool("pcb_inspect",
            "Capture only the bound Cadence window and return its PNG plus fresh before/after snapshots. Visually inspect this image; pixels alone do not prove DRC or electrical correctness.",
            schema({ session: sessionProperty }), "inspect", ["session"]),
        tool("pcb_prepare_placement",
            "Prepare one exact supported pose, including an unplaced component in a managed-board-v1 session, with current native PNG and snapshot evidence. Does not import, load libraries, place, move or approve. Targets are absolute millimeters and orthogonal degrees about the component origin.",
            schema({
                session: sessionProperty,
                refdes: { type: "string", pattern: "^[A-Za-z][A-Za-z0-9_]{0,30}$" },
                x: { type: "string", description: "Absolute X in millimeters; plain finite decimal." },
                y: { type: "string", description: "Absolute Y in millimeters; plain finite decimal." },
                angle: { type: "string", enum: ["0", "90", "180", "270"] },
            }), "prepare", ["session", "refdes", "x", "y", "angle"]),
        tool("pcb_execution_status",
            "Read/reconcile the native outcome of one proposal without resending it. Use after timeout or missing visual output, never blindly retry a placement.",
            schema({ session: sessionProperty, proposal: proposalProperty }),
            "execution-status", ["session", "proposal"]),
    ];
    tools.push({
        name: "pcb_inspection_status",
        description: "Report a pending read-only snapshot after a capture timeout. Supply its exact request ID to reconcile only that snapshot's late result. Never resends commands or reconciles a pending placement.",
        parameters: schema({
            session: sessionProperty,
            request: {
                type: "string", pattern: "^[0-9a-f]{32}$",
                description: "Optional exact pending read-only request ID reported by this tool or execution status.",
            },
        }, ["session"]),
        handler: async (args) => {
            try {
                requireFields(args, args && "request" in args ? ["session", "request"] : ["session"]);
                if ("request" in args && !/^[0-9a-f]{32}$/.test(args.request)) {
                    throw new Error("Expected the exact pending read-only request ID.");
                }
                return await render(await run({ action: "inspection-status", ...args }));
            } catch (error) {
                return {
                    resultType: "failure", textResultForLlm: JSON.stringify({
                        status: "error", error: error.message, retry_placement: false,
                    }),
                };
            }
        },
    });
    function visualWriteTool(name, description, describeAction, applyAction) {
        return {
        name, description,
        parameters: schema({ session: sessionProperty, proposal: proposalProperty }),
        handler: async (args) => {
            try {
                requireFields(args, ["session", "proposal"]);
                const description = await run({ action: describeAction, ...args });
                if (description.status !== "prepared") return await render(description);
                await imageResult(description.visual);
                return await render(await run({ action: applyAction, ...args }));
            } catch (error) {
                return {
                    resultType: "failure",
                    textResultForLlm: JSON.stringify({
                        status: "error", error: error.message,
                        warning: "Do not infer rollback or retry. Query this proposal's library/save status if dispatch was attempted.",
                    }),
                };
            }
        },
        };
    }
    tools.push(tool("pcb_apply_placement",
        "Autonomously apply one exact visually grounded proposal in memory. Native state is rechecked and dispatch is single-use; no arbitrary SKILL or implicit save.",
        schema({ session: sessionProperty, proposal: proposalProperty }),
        "apply", ["session", "proposal"]));
    tools.push(tool("pcb_prepare_save",
        "Prepare a visually bound new-revision save proposal. No Save or approval occurs.",
        schema({ session: sessionProperty }), "prepare-save", ["session"]));
    tools.push(tool("pcb_save_status",
        "Read or reconcile one exact Save outcome without resending. A saved revision is distinct from reopen verification.",
        schema({ session: sessionProperty, proposal: proposalProperty }),
        "save-status", ["session", "proposal"]));
    tools.push(visualWriteTool("pcb_save_revision",
        "Autonomously save one exact visually bound proposal as a new revision. Single-use dispatch; no source overwrite or automatic reopen.",
        "describe-save", "apply-save"));
    tools.push(tool("pcb_inspect_libraries",
        "Inspect the bound library-setup inventory and actual PNG before package definitions are embedded. This is not full placement readiness.",
        schema({ session: sessionProperty }), "inspect-libraries", ["session"]));
    tools.push(tool("pcb_prepare_library_load",
        "Prepare exact missing package definitions from verified staged files and fresh PNG evidence. No libraries are loaded or approved.",
        schema({ session: sessionProperty }), "prepare-libraries", ["session"]));
    tools.push(tool("pcb_library_load_status",
        "Read or reconcile the exact recorded library-load outcome without replaying it. Full board inspection is still required afterward.",
        schema({ session: sessionProperty, proposal: proposalProperty }),
        "library-status", ["session", "proposal"]));
    tools.push(visualWriteTool("pcb_load_libraries",
        "Autonomously load one exact visually bound set of verified staged definitions. Single-use dispatch; no placement, Save or global settings changes.",
        "describe-libraries", "load-libraries"));
    return tools;
}
