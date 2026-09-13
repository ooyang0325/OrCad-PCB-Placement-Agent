import base64
import importlib.util
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

from orcad_placement_agent.visuals import encode_png


AVAILABLE = importlib.util.find_spec("mcp") is not None
PROPOSAL = "a" * 64


class FakeActions:
    def __init__(self, root):
        self.root = root
        self.calls = []
        self.applied = set()
        self.saved = set()
        self.loaded = set()
        self.visual = {"observation_id": "b" * 32, "image_path": str(root / "fixture.png")}

    def dispatch(self, request):
        self.calls.append(request)
        action = request["action"]
        if action in {"describe", "describe-save", "describe-libraries"}:
            return {
                "status": "prepared", "summary": "R1: (10, 10) -> (12, 12), 90 degrees",
                "working_board": str(self.root / "working.brd"),
                "warning": "Memory only; not a save.", "visual": self.visual,
            }
        if action == "apply":
            if request["proposal"] in self.applied:
                return {"status": "error", "error": "Proposal dispatch was already consumed."}
            self.applied.add(request["proposal"])
            return {"status": "applied", "visual": self.visual, "receipt": {"status": "applied"}}
        if action == "apply-save":
            if request["proposal"] in self.saved:
                return {"status": "error", "error": "Save dispatch was already consumed."}
            self.saved.add(request["proposal"])
            return {"status": "saved", "visual": self.visual, "receipt": {"status": "saved"}, "reopened": False}
        if action == "load-libraries":
            if request["proposal"] in self.loaded:
                return {"status": "error", "error": "Library dispatch was already consumed."}
            self.loaded.add(request["proposal"])
            return {"status": "libraries_loaded", "visual": self.visual, "placement_ready": False, "saved": False}
        if action == "sessions":
            return {"status": "listed", "sessions": []}
        return {"status": "observed", "visual": self.visual, "scene_native": "OPA-FIXTURE-1;opaque"}


@unittest.skipUnless(AVAILABLE, "Install the optional integrations extra for MCP tests.")
class MCPServerTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from orcad_placement_agent.mcp_server import create_server

        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.actions = FakeActions(Path(self.temp.name))
        self.png = encode_png(2, 1, bytes([0, 0, 255, 0, 0, 255, 0, 0]))
        self.server = create_server(
            lambda: self.actions, image_reader=lambda _actions, _visual: self.png,
        )

    async def test_tool_catalog_exposes_autonomous_apply_images_and_recovery(self):
        from mcp import Client

        async with Client(self.server) as client:
            tools = (await client.list_tools()).tools
            names = {tool.name for tool in tools}
            self.assertEqual(names, {
                "pcb_sessions", "pcb_inspect", "pcb_prepare_placement", "pcb_apply_placement",
                "pcb_execution_status", "pcb_inspection_status", "pcb_reference_catalog",
                "pcb_reference_search", "pcb_reference_page", "pcb_reference_rule",
                "pcb_plan_placement", "pcb_placement_status", "pcb_prepare_next_placement",
                "pcb_prepare_save", "pcb_save_revision", "pcb_save_status",
                "pcb_inspect_libraries", "pcb_prepare_library_load", "pcb_load_libraries", "pcb_library_load_status",
                "pcb_placement_intake", "pcb_read_proposal",
            })
            apply = next(tool for tool in tools if tool.name == "pcb_apply_placement")
            self.assertEqual(set(apply.input_schema["properties"]), {"session", "proposal"})
            self.assertFalse(apply.annotations.read_only_hint)
            self.assertFalse(apply.annotations.idempotent_hint)
            result = await client.call_tool("pcb_inspect", {"session": "board-fixture"})
            self.assertFalse(result.is_error)
            image = next(block for block in result.content if block.type == "image")
            self.assertEqual(base64.b64decode(image.data), self.png)
            self.assertEqual(image.mime_type, "image/png")
            self.assertTrue(result.structured_content["scene_native"]["opaque_scene_omitted_from_display"])

    async def test_intake_and_proposal_images_are_read_only_without_elicitation(self):
        from mcp import Client

        async with Client(self.server) as client:
            tools = {tool.name: tool for tool in (await client.list_tools()).tools}
            for name, arguments, action in (
                ("pcb_placement_intake", {"session": "board-fixture"}, "intake"),
                ("pcb_read_proposal", {"session": "board-fixture", "proposal": PROPOSAL, "kind": "library"},
                 "read-proposal"),
            ):
                self.assertTrue(tools[name].annotations.read_only_hint)
                response = await client.call_tool(name, arguments)
                self.assertFalse(response.is_error)
                self.assertEqual(self.actions.calls[-1], {"action": action, **arguments})
                image = next(block for block in response.content if block.type == "image")
                self.assertEqual(base64.b64decode(image.data), self.png)
            count = len(self.actions.calls)
            response = await client.call_tool("pcb_read_proposal", {
                "session": "board-fixture", "proposal": PROPOSAL, "kind": "execute",
            })
            self.assertTrue(response.is_error)
            self.assertEqual(len(self.actions.calls), count)

    async def test_session_listing_exposes_declared_scope_without_native_access(self):
        from mcp import Client
        from orcad_placement_agent.agent_tools import AgentActions
        from orcad_placement_agent.mcp_server import create_server

        server = create_server(lambda: AgentActions(Path(self.temp.name)))
        async with Client(server) as client:
            result = await client.call_tool("pcb_sessions", {})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["sessions"], [])
            self.assertTrue(result.structured_content["capabilities"]["declaration_only"])
            self.assertEqual(result.structured_content["capabilities"]["initial_placement_model"], "managed-board-v1")

    async def test_apply_is_autonomous_in_either_protocol_mode(self):
        from mcp import Client

        for mode, proposal in [("legacy", "a" * 64), ("auto", "c" * 64)]:
            with self.subTest(mode=mode):
                async with Client(self.server, mode=mode) as client:
                    result = await client.call_tool(
                        "pcb_apply_placement", {"session": "board-fixture", "proposal": proposal}
                    )
                    self.assertFalse(result.is_error)
                    self.assertEqual(result.structured_content["status"], "applied")
        self.assertEqual(self.actions.applied, {"a" * 64, "c" * 64})

    async def test_default_install_applies_without_elicitation(self):
        from mcp import Client
        from mcp.types import ElicitResult
        from orcad_placement_agent.mcp_server import create_server

        prompts = []

        async def callback(_context, params):
            prompts.append(params)
            return ElicitResult(action="accept", content={"confirmation": f"APPLY {PROPOSAL}"})

        server = create_server(lambda: self.actions, image_reader=lambda _a, _v: self.png)
        async with Client(server, elicitation_callback=callback) as client:
            result = await client.call_tool("pcb_apply_placement", {
                "session": "board-fixture", "proposal": PROPOSAL,
            })
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["status"], "applied")
        self.assertEqual(prompts, [])
        self.assertEqual(self.actions.applied, {PROPOSAL})

    async def test_load_and_save_work_without_elicitation_in_both_protocol_modes(self):
        from mcp import Client

        for mode, proposal in (("legacy", "a" * 64), ("auto", "b" * 64)):
            async with Client(self.server, mode=mode) as client:
                tools = {tool.name: tool for tool in (await client.list_tools()).tools}
                for name, action, status in (("pcb_load_libraries", "load-libraries", "libraries_loaded"),
                                             ("pcb_save_revision", "apply-save", "saved")):
                    with self.subTest(mode=mode, tool=name):
                        self.assertEqual(set(tools[name].input_schema["properties"]), {"session", "proposal"})
                        self.assertFalse(tools[name].annotations.read_only_hint)
                        self.assertFalse(tools[name].annotations.idempotent_hint)
                        response = await client.call_tool(name, {"session": "board-fixture", "proposal": proposal})
                        self.assertFalse(response.is_error)
                        self.assertEqual(response.structured_content["status"], status)
                        self.assertEqual(self.actions.calls[-1], {"action": action, "session": "board-fixture",
                                                                 "proposal": proposal})
                        if status == "saved":
                            self.assertFalse(response.structured_content["reopened"])
                        else:
                            self.assertFalse(response.structured_content["placement_ready"])
                        replay = await client.call_tool(name, {"session": "board-fixture", "proposal": proposal})
                        self.assertTrue(replay.is_error)
        self.assertFalse(self.actions.applied)
        self.assertEqual(self.actions.saved, {"a" * 64, "b" * 64})
        self.assertEqual(self.actions.loaded, {"a" * 64, "b" * 64})

    async def test_legacy_approval_parameters_do_not_reach_dispatch(self):
        from mcp import Client

        async with Client(self.server) as client:
            result = await client.call_tool("pcb_apply_placement", {
                "session": "board-fixture", "proposal": PROPOSAL,
                "confirmation": f"APPLY {PROPOSAL}",
                "decision": {"action": "accept", "data": {"confirmation": f"APPLY {PROPOSAL}"}},
            })
            self.assertFalse(result.is_error)
        self.assertEqual(self.actions.applied, {PROPOSAL})
        apply = next(call for call in self.actions.calls if call["action"] == "apply")
        self.assertEqual(set(apply), {"action", "session", "proposal"})

    async def test_image_failure_preserves_recorded_native_outcome(self):
        from mcp import Client
        from orcad_placement_agent.mcp_server import create_server
        from orcad_placement_agent.visuals import VisualError

        def image(_actions, _visual):
            if self.actions.applied:
                raise VisualError("Post-image unavailable")
            return self.png

        server = create_server(lambda: self.actions, image_reader=image, allow_interactive_writes=True)
        async with Client(server) as client:
            result = await client.call_tool(
                "pcb_apply_placement", {"session": "board-fixture", "proposal": PROPOSAL}
            )
            self.assertTrue(result.is_error)
            self.assertEqual(result.structured_content["status"], "applied")
            self.assertIn("image_error", result.structured_content)
        self.assertEqual(len(self.actions.applied), 1)

    async def test_invalid_inputs_and_optional_original_pages_are_explicit(self):
        from mcp import Client

        async with Client(self.server) as client:
            result = await client.call_tool("pcb_inspect", {"session": "../outside"})
            self.assertTrue(result.is_error)
            self.assertEqual(self.actions.calls, [])
            result = await client.call_tool("pcb_reference_catalog", {})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["data"]["bundled"]["card_count"], 36)
            result = await client.call_tool("pcb_reference_search", {"query": "decoupling"})
            self.assertFalse(result.is_error)
            card_id = result.structured_content["data"]["hits"][0]["card_id"]
            result = await client.call_tool("pcb_reference_rule", {"card_id": card_id})
            self.assertFalse(result.is_error)
            self.assertTrue(result.structured_content["data"]["checks"])
            result = await client.call_tool("pcb_reference_page", {"source": "original.pdf", "page": 1})
            self.assertTrue(result.is_error)
            self.assertIn("not bundled", result.structured_content["error"])
            self.assertEqual(self.actions.calls, [])

    async def test_real_stdio_entrypoint_runs_without_repository_cwd(self):
        from mcp import Client, StdioServerParameters

        environment = dict(os.environ)
        environment.pop("OPA_KNOWLEDGE_DB", None)
        parameters = StdioServerParameters(
            command=sys.executable, args=["-I", "-X", "utf8", "-m", "orcad_placement_agent.mcp_server"],
            cwd=self.temp.name, env=environment,
        )
        async with Client(parameters, mode="legacy", read_timeout_seconds=15) as client:
            self.assertEqual(len((await client.list_tools()).tools), 22)
            result = await client.call_tool("pcb_reference_catalog", {})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["data"]["bundled"]["card_count"], 36)

    async def test_legacy_flag_cannot_gate_load_save_or_request_human_input(self):
        from mcp import Client
        from mcp.types import ElicitResult
        from orcad_placement_agent.mcp_server import create_server

        prompts = []

        async def callback(_context, params):
            prompts.append(params.message)
            return ElicitResult(action="decline")

        for flag, proposal in ((False, "a" * 64), (True, "b" * 64)):
            server = create_server(lambda: self.actions, image_reader=lambda _a, _v: self.png,
                                   allow_interactive_writes=flag)
            async with Client(server, elicitation_callback=callback) as client:
                for tool in ("pcb_load_libraries", "pcb_save_revision"):
                    response = await client.call_tool(tool, {"session": "board-fixture", "proposal": proposal})
                    self.assertFalse(response.is_error)
        self.assertEqual(prompts, [])

    async def test_load_save_reject_invalid_proposals_and_missing_visual_binding(self):
        from mcp import Client

        async with Client(self.server) as client:
            for tool in ("pcb_load_libraries", "pcb_save_revision"):
                result = await client.call_tool(tool, {"session": "board-fixture", "proposal": "invalid"})
                self.assertTrue(result.is_error)
            self.assertEqual(self.actions.calls, [])
            self.actions.visual = None
            for tool in ("pcb_load_libraries", "pcb_save_revision"):
                result = await client.call_tool(tool, {"session": "board-fixture", "proposal": PROPOSAL})
                self.assertTrue(result.is_error)
                self.assertFalse(result.structured_content["dispatched"])
        self.assertFalse(self.actions.loaded or self.actions.saved)

    async def test_load_save_image_failure_blocks_before_dispatch_but_preserves_post_outcome(self):
        from mcp import Client
        from orcad_placement_agent.mcp_server import create_server
        from orcad_placement_agent.visuals import VisualError

        missing_before = True

        def image(_actions, _visual):
            if missing_before or self.actions.loaded or self.actions.saved:
                raise VisualError("Library image unavailable")
            return self.png

        for tool, action, status in (("pcb_load_libraries", "load-libraries", "libraries_loaded"),
                                     ("pcb_save_revision", "apply-save", "saved")):
            self.actions = FakeActions(Path(self.temp.name))
            missing_before = True
            server = create_server(lambda: self.actions, image_reader=image)
            async with Client(server) as client:
                response = await client.call_tool(tool, {"session": "board-fixture", "proposal": PROPOSAL})
                self.assertTrue(response.is_error)
                self.assertFalse(self.actions.loaded or self.actions.saved)
                missing_before = False
                response = await client.call_tool(tool, {"session": "board-fixture", "proposal": PROPOSAL})
                self.assertTrue(response.is_error)
                self.assertEqual(response.structured_content["status"], status)
                self.assertIn("image_error", response.structured_content)
            self.assertEqual(sum(call["action"] == action for call in self.actions.calls), 1)

    async def test_zero_placed_mission_and_separate_save_through_real_mcp_with_fake_editor(self):
        from mcp import Client
        from mcp.types import ElicitResult
        from orcad_placement_agent.agent_tools import AgentActions
        from orcad_placement_agent.mcp_server import create_server
        from tests.test_mission_actions import FakeManagedEditor

        root = Path(self.temp.name)
        board_root = root / "board-loop"
        board_root.mkdir()
        editor = FakeManagedEditor(board_root)
        actions = AgentActions(root, session_factory=lambda _path: editor, capture=editor.capture)
        prompts = []

        async def fake_human(_context, params):
            prompts.append(params.message)
            return ElicitResult(action="decline")

        server = create_server(lambda: actions,
                               image_reader=lambda _a, visual: Path(visual["image_path"]).read_bytes())
        async with Client(server, elicitation_callback=fake_human) as client:
            result = await client.call_tool("pcb_plan_placement", {
                "session": "board-loop",
                "requirements_json": json.dumps({"expected_refdes": ["U1", "U2", "R1"],
                                                  "grid_mm": "1", "clearance_mm": "0.5"}),
            })
            self.assertFalse(result.is_error)
            mission = result.structured_content["mission"]
            for _ in range(3):
                result = await client.call_tool("pcb_prepare_next_placement", {
                    "session": "board-loop", "mission": mission,
                })
                self.assertFalse(result.is_error)
                proposal = result.structured_content["proposal_sha256"]
                result = await client.call_tool("pcb_apply_placement", {"session": "board-loop", "proposal": proposal})
                self.assertFalse(result.is_error)
                self.assertEqual(result.structured_content["status"], "applied")
            result = await client.call_tool("pcb_placement_status", {"session": "board-loop", "mission": mission})
            self.assertTrue(result.structured_content["progress"]["placement"]["complete"])
            self.assertEqual(result.structured_content["progress"]["routing"]["verification"], "unverified")
            result = await client.call_tool("pcb_prepare_save", {"session": "board-loop"})
            proposal = result.structured_content["proposal_sha256"]
            result = await client.call_tool("pcb_save_revision", {"session": "board-loop", "proposal": proposal})
            self.assertFalse(result.is_error)
            self.assertEqual(result.structured_content["status"], "saved")
            self.assertFalse(result.structured_content["reopened"])
        self.assertEqual(prompts, [])
        self.assertEqual([request.operation for request in editor.requests], ["apply", "apply", "apply", "save"])


if __name__ == "__main__":
    unittest.main()
