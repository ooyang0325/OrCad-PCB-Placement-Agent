import os
from pathlib import Path
import shutil
import subprocess
import unittest


SCRIPT = r"""
import assert from "node:assert/strict";
import { pathToFileURL } from "node:url";
const { createPlacementTools } = await import(pathToFileURL(process.argv[1]));
const digest = "a".repeat(64);
const args = { session: "board-fixture", proposal: digest };
const visual = { observation_id: "b".repeat(32), image_path: "fixture.png" };
function harness({ supported = true, answer = null, imageFailure = false, preImageFailure = false,
    loadStatus = "libraries_loaded" } = {}) {
    const requests = [];
    const prompts = [];
    const tools = createPlacementTools({
        canPrompt: () => supported,
        requestInput: async (message, options) => {
            prompts.push({ message, options });
            return answer;
        },
        run: async (request) => {
            requests.push(request);
            return ["describe", "describe-save", "describe-libraries"].includes(request.action)
                ? { status: "prepared", summary: "R1 (10,10) -> (12,12), 90 degrees",
                    working_board: "working.brd", warning: "Memory only", visual }
                : { status: request.action === "apply" ? "applied" :
                    request.action === "apply-save" ? "saved" :
                    request.action === "load-libraries" ? loadStatus : "observed", visual };
        },
        imageResult: async () => {
            if (preImageFailure || (imageFailure && requests.some(r =>
                ["apply", "apply-save", "load-libraries"].includes(r.action)))) throw new Error("Image unavailable");
            return { type: "image", mimeType: "image/png", data: "test" };
        },
    });
    return { requests, prompts, tools, apply: tools.find(t => t.name === "pcb_apply_placement") };
}
let h = harness({ supported: false });
assert.equal((await h.apply.handler(args)).resultType, "success");
assert.equal(h.requests[0].action, "apply");
h = harness();
assert.equal((await h.apply.handler({ ...args, confirmation: `APPLY ${digest}` })).resultType, "failure");
assert.equal(h.prompts.length, 0);
assert.equal(h.requests.length, 0);
for (const [name, action] of [["pcb_save_revision", "apply-save"], ["pcb_load_libraries", "load-libraries"]]) {
    h = harness({ supported: false });
    const tool = h.tools.find(t => t.name === name);
    assert.equal((await tool.handler(args)).resultType, "success");
    assert.deepEqual(h.requests[1], { action, ...args });
    assert.equal(h.prompts.length, 0);
    assert.deepEqual(Object.keys(tool.parameters.properties), ["session", "proposal"]);
    const count = h.requests.length;
    assert.equal((await tool.handler({ ...args, confirmation: "yes" })).resultType, "failure");
    assert.equal(h.requests.length, count);
}
for (const loadStatus of ["libraries_loaded", "library_partial"]) {
    h = harness({ answer: `LOAD ${digest}`, loadStatus });
    const result = await h.tools.find(t => t.name === "pcb_load_libraries").handler(args);
    assert.equal(result.resultType, loadStatus === "library_partial" ? "failure" : "success");
    assert.equal(h.requests[1].action, "load-libraries");
    assert.equal("confirmation" in h.requests[1], false);
    assert.equal(h.prompts.length, 0);
    assert.equal(JSON.parse(result.textResultForLlm).status, loadStatus);
}
h = harness({ answer: `LOAD ${digest}`, imageFailure: true });
const libraryImage = await h.tools.find(t => t.name === "pcb_load_libraries").handler(args);
assert.equal(libraryImage.resultType, "failure");
assert.equal(JSON.parse(libraryImage.textResultForLlm).status, "libraries_loaded");
assert.equal(h.requests.filter(r => r.action === "load-libraries").length, 1);
for (const [name, verb] of [["pcb_load_libraries", "LOAD"], ["pcb_save_revision", "SAVE"],
    ["pcb_apply_placement", "APPLY"]]) {
    h = harness({ answer: `${verb} ${digest}`, preImageFailure: true });
    assert.equal((await h.tools.find(t => t.name === name).handler(args)).resultType, "failure");
    assert.equal(h.prompts.length, 0);
    assert.equal(h.requests.length, 1);
}
h = harness({ answer: "yes" });
const outcome = await h.apply.handler(args);
assert.equal(outcome.resultType, "success");
assert.equal(h.requests[0].action, "apply");
assert.equal("confirmation" in h.requests[0], false);
assert.equal(outcome.binaryResultsForLlm[0].type, "image");
h = harness({ answer: `APPLY ${digest}`, imageFailure: true });
const failedImage = await h.apply.handler(args);
assert.equal(failedImage.resultType, "failure");
assert.equal(JSON.parse(failedImage.textResultForLlm).status, "applied");
assert.equal(h.requests.filter(r => r.action === "apply").length, 1);
for (const tool of h.tools) assert.equal(tool.parameters.additionalProperties, false);
assert.deepEqual(Object.keys(h.apply.parameters.properties), ["session", "proposal"]);
h = harness({ supported: false });
for (const [name, parameters, action] of [
    ["pcb_placement_intake", { session: args.session }, "intake"],
    ["pcb_read_proposal", { ...args, kind: "library" }, "read-proposal"],
    ["pcb_review_proposal", { ...args, kind: "placement" }, "review-proposal"],
]) {
    const tool = h.tools.find(t => t.name === name);
    const result = await tool.handler(parameters);
    assert.equal(result.resultType, "success");
    assert.deepEqual(h.requests.at(-1), { action, ...parameters });
    assert.equal(result.binaryResultsForLlm[0].type, "image");
    const count = h.requests.length;
    assert.equal((await tool.handler({ ...parameters, confirmation: "yes" })).resultType, "failure");
    assert.equal(h.requests.length, count);
}
assert.equal(h.prompts.length, 0);
h = harness({ preImageFailure: true });
assert.equal((await h.tools.find(t => t.name === "pcb_read_proposal").handler({
    ...args, kind: "placement",
})).resultType, "failure");
assert.equal(h.requests.length, 1);
assert.equal(h.requests[0].action, "read-proposal");
h = harness();
for (const [name, args, action] of [
    ["pcb_reference_catalog", {}, "reference-catalog"],
    ["pcb_reference_search", { query: "decoupling" }, "reference-search"],
    ["pcb_reference_rule", { card_id: "pt-example" }, "reference-rule"],
]) {
    const tool = h.tools.find(t => t.name === name);
    assert.ok(tool);
    assert.equal((await tool.handler(args)).resultType, "success");
    assert.equal(h.requests.at(-1).action, action);
    assert.equal((await tool.handler({ ...args, database: "outside" })).resultType, "failure");
}
assert.equal(h.prompts.length, 0);
let modeChecks = 0;
let dispatched = false;
for (const [name, verb, action] of [
    ["pcb_load_libraries", "LOAD", "load-libraries"], ["pcb_save_revision", "SAVE", "apply-save"]]) {
modeChecks = 0;
dispatched = false;
const switched = createPlacementTools({
    canPrompt: async () => ++modeChecks === 1,
    requestInput: async () => `${verb} ${digest}`,
    imageResult: async () => ({ type: "image", mimeType: "image/png", data: "test" }),
    run: async (request) => {
        if (request.action === action) dispatched = true;
        return { status: "prepared", summary: "exact proposal", working_board: "working.brd",
            warning: "Memory only", visual };
    },
}).find(t => t.name === name);
assert.equal((await switched.handler(args)).resultType, "success");
assert.equal(dispatched, true);
assert.equal(modeChecks, 0);
}
console.log("Autonomous placement, LOAD/SAVE and image-outcome cases passed.");
"""


class ExtensionToolTests(unittest.TestCase):
    def test_placement_load_and_save_are_autonomous_with_visual_checks(self):
        node = os.environ.get("OPA_NODE") or shutil.which("node")
        if not node or not Path(node).is_file():
            self.skipTest("Set OPA_NODE to an existing Node.js 20+ executable for extension tests.")
        root = Path(__file__).resolve().parents[1]
        module = root / ".github" / "extensions" / "pcb-placement" / "operations.mjs"
        result = subprocess.run(
            [node, "--input-type=module", "-e", SCRIPT, str(module)],
            cwd=root, capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
