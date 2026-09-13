import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock

from orcad_placement_agent import __version__
from orcad_placement_agent.agent_tools import AgentActions
from orcad_placement_agent.capabilities import backend_capabilities
from orcad_placement_agent.protocol import OPERATIONS
from orcad_placement_agent.transport import CommandTransport


class OrchestrationContractTests(unittest.TestCase):
    def test_capabilities_declare_conditional_initial_placement_not_live_readiness(self):
        capabilities = backend_capabilities()
        self.assertEqual(capabilities["implementation_version"], __version__)
        self.assertTrue(capabilities["declaration_only"])
        self.assertEqual(capabilities["default_native_model"], "fixture")
        self.assertEqual(capabilities["initial_placement_model"], "managed-board-v1")
        self.assertTrue(capabilities["initial_component_placement"])
        self.assertTrue(capabilities["placement_missions"])
        self.assertIn("live acceptance", capabilities["native_acceptance"])
        for name in (
            "logical_design_import", "agent_undo",
            "arbitrary_board_writes", "route_generation",
            "routing_feasibility_verification", "human_approval_required",
        ):
            self.assertFalse(capabilities[name], name)
        self.assertTrue(capabilities["move_existing_component"])
        self.assertTrue(capabilities["model_can_authorize_changes"])
        self.assertTrue(capabilities["portable_writes_enabled_by_default"])
        self.assertFalse(capabilities["save_human_approval_required"])
        self.assertFalse(capabilities["library_human_approval_required"])
        self.assertTrue(capabilities["placement_intake_routing"])
        self.assertTrue(capabilities["archived_proposal_images"])
        self.assertFalse(capabilities["agent_editor_setup"])
        self.assertTrue(capabilities["unattended_library_loading"])
        self.assertTrue(capabilities["unattended_revision_save"])
        self.assertIn("OBLONG_X", capabilities["supported_smt_pad_figures"])
        self.assertIn("ROUNDED_RECTANGLE", capabilities["supported_smt_pad_figures"])
        self.assertNotIn("SHAPE", capabilities["supported_smt_pad_figures"])
        self.assertNotIn("place", OPERATIONS)
        self.assertNotIn("import", OPERATIONS)
        self.assertNotIn("route", OPERATIONS)
        self.assertNotIn("opa_place", CommandTransport.COMMANDS)

    def test_empty_session_listing_is_not_readiness_or_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            factory = Mock(side_effect=AssertionError("No live session should be probed."))
            service = AgentActions(Path(directory), session_factory=factory)
            result = service.dispatch({"action": "sessions"})
            self.assertEqual(result["sessions"], [])
            self.assertTrue(result["capabilities"]["declaration_only"])
            self.assertEqual(result["capabilities"]["initial_placement_model"], "managed-board-v1")
            factory.assert_not_called()

    def test_capability_payloads_cannot_change_the_shared_declaration(self):
        first = backend_capabilities()
        first["initial_component_placement"] = False
        first["supported_target_angles"].append(45)
        second = backend_capabilities()
        self.assertTrue(second["initial_component_placement"])
        self.assertEqual(second["supported_target_angles"], [0, 90, 180, 270])

    def test_coordinator_has_delegation_but_no_direct_execution_authority(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "agents" / "pcb-placement-orchestrator.agent.md").read_text(encoding="utf-8")
        frontmatter, body = text.split("---", 2)[1:]
        body = " ".join(body.split())
        fields = dict(line.split(":", 1) for line in frontmatter.splitlines() if line.strip())
        tools = set(json.loads(fields["tools"]))
        self.assertTrue({"agent", "todo", "pcb_inspect", "pcb_sessions",
                         "pcb_placement_intake", "pcb_read_proposal"} <= tools)
        self.assertFalse({"execute", "edit", "web", "pcb_apply_placement", "pcb_prepare_placement"} & tools)
        self.assertEqual(fields["disable-model-invocation"].strip(), "true")
        for worker in ("PCB placement planner", "PCB layout reviewer", "PCB placement executor"):
            self.assertIn(worker, body)
        self.assertIn("0/0 is not completion", body)
        self.assertIn("initial-placement capability gap", body)
        self.assertIn("routability", body)

    def test_both_coordinator_surfaces_require_routing_visual_and_handoff_gates(self):
        root = Path(__file__).resolve().parents[1]
        paths = [
            root / ".github" / "agents" / "pcb-placement-orchestrator.agent.md",
            root / "skills" / "pcb-placement-orchestrate" / "SKILL.md",
        ]
        for path in paths:
            text = " ".join(path.read_text(encoding="utf-8").lower().split())
            for requirement in (
                "png", "observation", "inventory", "unplaced", "fanout",
                "corridor", "congestion", "reference", "thermal", "test access",
                "independent", "not completion", "routability", "unverified",
                "approval", "untrusted", "blocked",
            ):
                self.assertIn(requirement, text, f"{path.name}: {requirement}")

    def test_continuous_driver_recovers_supported_handoffs_without_manual_relay(self):
        root = Path(__file__).resolve().parents[1]
        for path in (root / ".github" / "agents" / "pcb-placement-orchestrator.agent.md",
                     root / "skills" / "pcb-placement-orchestrate" / "SKILL.md"):
            text = " ".join(path.read_text(encoding="utf-8").split())
            for requirement in ("Continuous mission driver", "pcb_placement_intake", "setup_required",
                                "intake_ready", "pcb_read_proposal", "libraries_loaded", "independent",
                                '"continue"', "without per-operation human approval",
                                "session and fixture preparation", "Unsupported features"):
                self.assertIn(requirement, text)
            for obsolete in ("separate LOAD/SAVE approval", "requests genuine human LOAD",
                             "executor for genuine human LOAD approval"):
                self.assertNotIn(obsolete, text)
        for name in ("pcb-layout-reviewer", "pcb-placement-executor"):
            text = (root / ".github" / "agents" / f"{name}.agent.md").read_text(encoding="utf-8")
            fields = dict(line.split(":", 1) for line in text.split("---", 2)[1].splitlines() if line.strip())
            tools = json.loads(fields["tools"])
            self.assertIn("pcb_read_proposal", tools)
            if name == "pcb-layout-reviewer":
                self.assertNotIn("execute", tools)
                self.assertNotIn("edit", tools)
            else:
                self.assertTrue({"execute", "edit"} <= set(tools))

    def test_executor_can_provision_and_execute_with_recovery(self):
        root = Path(__file__).resolve().parents[1]
        text = (root / ".github" / "agents" / "pcb-placement-executor.agent.md").read_text(encoding="utf-8")
        frontmatter, body = text.split("---", 2)[1:]
        fields = dict(line.split(":", 1) for line in frontmatter.splitlines() if line.strip())
        tools = set(json.loads(fields["tools"]))
        self.assertTrue({"read", "search", "edit", "execute", "agent",
                         "pcb_prepare_library_load", "pcb_load_libraries",
                         "pcb_prepare_save", "pcb_save_revision"} <= tools)
        self.assertEqual(set(json.loads(fields["agents"])),
                         {"PCB placement planner", "PCB layout reviewer"})
        body = " ".join(body.split())
        for requirement in (
            "without per-operation human approval", "raw SKILL", "launch Cadence",
            "fixtures\\access-proof\\README.md", "recoverable baseline",
            "native readback", "Do not replay", "Host permissions", "disposable fixture",
            "MCP LOAD/SAVE dispatches autonomously",
            "Software tests do not establish native acceptance",
        ):
            self.assertIn(requirement, body)
        for obsolete in ("only to request its genuine human LOAD approval",
                         "human SAVE prompt", "No shell execution"):
            self.assertNotIn(obsolete, body)


if __name__ == "__main__":
    unittest.main()
