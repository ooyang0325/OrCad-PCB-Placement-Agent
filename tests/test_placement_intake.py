"""Read-only mission intake routing, with no licensed editor or implicit writes."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock
import uuid

from orcad_placement_agent.agent_tools import AgentActions, AgentActionError
from orcad_placement_agent.protocol import Receipt, ProtocolError
from orcad_placement_agent.transport import IndeterminateDelivery
from orcad_placement_agent.session import SessionError
from orcad_placement_agent.visuals import encode_png
from tests.test_board import managed_snapshot
from tests.test_library_load import library_snapshot


class PlacementIntakeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        board = self.root / "board-intake"
        board.mkdir()
        (board / "editor.json").write_text("{}", encoding="utf-8")
        self.session = Mock(root=board, model="managed-board-v1", nonce="1" * 32,
                            working=board / "working.brd", design_copy={})
        base = managed_snapshot()
        self.snapshot = replace(base, nonce=self.session.nonce, records=tuple(
            ("board", str(self.session.working)) if row[0] == "board" else row for row in base.records
        ))
        self.session.exchange.return_value = self.snapshot
        self.session._read_json.side_effect = lambda name: json.loads((board / name).read_text(encoding="utf-8"))
        self.capture = Mock(side_effect=lambda _session: self.observation(self.snapshot))
        self.library_capture = Mock(side_effect=lambda _session: self.observation(library_snapshot(self.session)))
        self.actions = AgentActions(self.root, session_factory=lambda _path: self.session,
                                    capture=self.capture, library_capture=self.library_capture)

    def observation(self, receipt):
        observation_id = uuid.uuid4().hex
        image = self.session.root / f"visual-{observation_id}.png"
        image.write_bytes(encode_png(1, 1, bytes(4)))
        (self.session.root / f"{receipt.request_id}.receipt.json").write_text(
            json.dumps(receipt.to_dict()), encoding="utf-8")
        return {"observation_id": observation_id, "image_path": str(image),
                "after_request_id": receipt.request_id}

    def call(self):
        return self.actions.dispatch({"action": "intake", "session": "board-intake"})

    def reject(self, message):
        self.session.exchange.return_value = Receipt(self.session.nonce, "a" * 32, "rejected", message, ())

    def test_ready_board_returns_native_inventory_and_explicit_requirements(self):
        result = self.call()
        self.assertEqual(result["status"], "intake_ready")
        self.assertTrue(result["placement_ready"])
        self.assertEqual(result["next_tool"], "pcb_plan_placement")
        self.assertEqual(result["required_inputs"], ["expected_refdes", "grid_mm", "clearance_mm"])
        self.assertEqual([part["refdes"] for part in result["board"]["components"]], ["U1"])
        self.assertTrue(Path(result["visual"]["image_path"]).is_file())
        self.assertEqual(self.session.exchange.call_args.args[0].operation, "snapshot")
        self.library_capture.assert_not_called()

    def test_missing_packages_route_to_preparation_without_loading(self):
        self.reject("Missing embedded package definitions (2); first required package: PART_A.")
        result = self.call()
        self.assertEqual(result["status"], "setup_required")
        self.assertEqual(result["inventory"]["missing_packages"], ["PART_A", "PART_B"])
        self.assertEqual(result["next_role"], "PCB placement planner")
        self.assertEqual(result["next_tool"], "pcb_prepare_library_load")
        self.assertFalse(result["placement_ready"])
        self.capture.assert_not_called()
        self.library_capture.assert_called_once()
        self.session.exchange.assert_called_once()
        self.assertEqual(list(self.session.root.glob("*approval*")), [])

    def test_native_padstack_failure_is_not_retried_as_library_setup(self):
        message = "Padstack VIA: unsupported isThrough=t."
        self.reject(message)
        result = self.call()
        self.assertEqual(result["phase"], "native_model_rejected")
        self.assertEqual(result["error"], message)
        self.assertNotIn("visual", result)
        self.assertFalse(result["placement_ready"])
        self.capture.assert_not_called()
        self.library_capture.assert_not_called()

    def test_unbound_and_fixture_sessions_block_without_native_access(self):
        self.session.model = "fixture"
        self.assertEqual(self.call()["phase"], "unsupported_model")
        self.session.model = "managed-board-v1"
        (self.session.root / "editor.json").unlink()
        self.assertEqual(self.call()["phase"], "attachment_required")
        self.session.exchange.assert_not_called()

    def test_pending_operations_are_not_replayed_or_cleared(self):
        pending = self.session.root / "pending.json"
        for operation in ("apply", "snapshot", "library_snapshot", "load_libraries", "save"):
            record = {"request_id": "d" * 32, "operation": operation}
            pending.write_text(json.dumps(record), encoding="utf-8")
            result = self.call()
            self.assertEqual(result["phase"], "reconciliation_required")
            self.assertEqual(result["request"], record["request_id"])
            self.assertEqual(json.loads(pending.read_text(encoding="utf-8")), record)
        self.session.exchange.assert_not_called()
        self.capture.assert_not_called()
        self.library_capture.assert_not_called()

    def test_timeouts_source_changes_and_missing_images_never_trigger_fallback(self):
        for error in (IndeterminateDelivery("Unknown result"), SessionError("Source changed")):
            self.session.exchange.side_effect = error
            with self.assertRaises(type(error)):
                self.call()
        self.session.exchange.side_effect = None
        self.capture.side_effect = AgentActionError("Image unavailable")
        with self.assertRaises(AgentActionError):
            self.call()
        self.library_capture.assert_not_called()

    def test_changed_scene_and_invalid_geometry_do_not_report_readiness(self):
        self.capture.side_effect = lambda _session: self.observation(replace(
            self.snapshot, records=tuple(
                ("scene", "OPA-BOARD-1;changed") if row[0] == "scene" else row
                for row in self.snapshot.records if row[0] != "scene-part"
            )))
        self.assertEqual(self.call()["phase"], "native_state_changed")
        self.snapshot = replace(self.snapshot, records=tuple(
            row for row in self.snapshot.records if row[0] != "component"
        ))
        self.session.exchange.return_value = self.snapshot
        self.capture.side_effect = lambda _session: self.observation(self.snapshot)
        with self.assertRaises(ProtocolError):
            self.call()

    def test_setup_race_or_unavailable_assets_never_certify_placement(self):
        self.reject("Missing embedded package definitions (2); first required package: PART_A.")
        self.library_capture.side_effect = lambda _session: self.observation(
            library_snapshot(self.session, existing=("PART_A", "PART_B")))
        self.assertEqual(self.call()["phase"], "native_state_changed")
        self.session.design_copy = None
        self.library_capture.reset_mock()
        self.assertEqual(self.call()["phase"], "native_model_rejected")
        self.library_capture.assert_not_called()

    def test_confirmed_library_setup_advances_to_full_planning_on_same_binding(self):
        self.reject("Missing embedded package definitions (2); first required package: PART_A.")
        self.assertEqual(self.call()["phase"], "library_preparation")
        self.session.exchange.return_value = self.snapshot
        ready = self.call()
        self.assertEqual(ready["phase"], "placement_planning")
        self.assertEqual(ready["session"], "board-intake")
        self.assertTrue((self.session.root / "editor.json").is_file())
        self.assertEqual([call.args[0].operation for call in self.session.exchange.call_args_list],
                         ["snapshot", "snapshot"])
        self.library_capture.assert_called_once()
        self.capture.assert_called_once()

    def test_intake_rejects_injected_parameters(self):
        with self.assertRaises(AgentActionError):
            self.actions.dispatch({"action": "intake", "session": "board-intake", "load": "yes"})
        self.session.exchange.assert_not_called()

    def test_consumed_dispatch_without_pending_file_blocks_native_intake(self):
        (self.session.root / f"dispatch-{'a' * 64}.json").write_text(json.dumps({
            "proposal_sha256": "a" * 64, "request_id": "d" * 32,
        }), encoding="utf-8")
        result = self.call()
        self.assertEqual(result["phase"], "execution_reconciliation")
        self.assertEqual(result["next_tool"], "pcb_execution_status")
        self.assertFalse(result["placement_ready"])
        self.session.exchange.assert_not_called()
        self.capture.assert_not_called()


if __name__ == "__main__":
    unittest.main()
