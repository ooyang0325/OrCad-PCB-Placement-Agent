from pathlib import Path
import json
import tempfile
import unittest
from unittest.mock import patch

from orcad_placement_agent.protocol import ProtocolError, Receipt
from orcad_placement_agent.proposals import (
    apply_proposal, load_dispatch_record, load_proposal, placement_dispatch_history,
    propose, proposal_summary, read_placement_receipt,
)
from orcad_placement_agent.session import SessionError, write_json


class FakeSession:
    nonce = "1" * 32

    def __init__(self, root):
        self.root = root
        self.requests = []

    def _read_json(self, name):
        return json.loads((self.root / name).read_text(encoding="utf-8"))

    def exchange(self, request):
        self.requests.append(request)
        return Receipt(self.nonce, request.request_id, "applied", "Applied", ())


class ProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.session = FakeSession(Path(self.temp.name))

    def snapshot(self, *, fixed="0", extra=()):
        return Receipt("1" * 32, "2" * 32, "snapshot", "Read complete", (
            ("snapshot", "2" * 32), ("board", r"C:\fixture\working.brd"),
            ("units", "millimeters", "3", "1000"), ("version", "25.1"),
            ("scene", "all components, bounds, nets and rule settings"),
            ("component", "R1", "fixture", "10", "10", "0", "0", fixed, "1"),
            *extra,
        ))

    def test_target_is_quantized_and_summary_discloses_actual_target(self):
        digest, proposal = propose(self.session, self.snapshot(), "R1", "12.0004", "10", "90")
        self.assertEqual(proposal["x"], "12")
        self.assertIn("memory only", proposal_summary(proposal))
        self.assertEqual(load_proposal(self.session, digest), proposal)

    def test_fixed_missing_noop_and_unsupported_angle_rejected(self):
        cases = [
            (self.snapshot(fixed="1"), "R1", "12", "10", "0"),
            (self.snapshot(), "R2", "12", "10", "0"),
            (self.snapshot(), "R1", "10", "10", "0"),
            (self.snapshot(), "R1", "12", "10", "45"),
        ]
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(ProtocolError):
                    propose(self.session, *args)

    def test_other_component_state_is_bound_to_proposal(self):
        first = propose(self.session, self.snapshot(), "R1", "12", "10", "90")[0]
        changed = self.snapshot(extra=(
            ("component", "R2", "fixture", "20", "10", "0", "0", "0", "1"),
        ))
        second = propose(self.session, changed, "R1", "12", "10", "90")[0]
        self.assertNotEqual(first, second)

    def test_duplicate_refdes_is_rejected(self):
        extra = (("component", "R1", "fixture", "20", "10", "0", "0", "0", "1"),)
        with self.assertRaises(ProtocolError):
            propose(self.session, self.snapshot(extra=extra), "R1", "12", "10", "0")

    def test_modified_proposal_cannot_be_dispatched(self):
        digest, proposal = propose(self.session, self.snapshot(), "R1", "12", "10", "0")
        proposal["x"] = "99"
        (self.session.root / f"proposal-{digest}.json").write_text(
            json.dumps(proposal), encoding="utf-8"
        )
        with self.assertRaises(ProtocolError):
            apply_proposal(self.session, digest)
        self.assertEqual(self.session.requests, [])

    def test_proposal_can_be_dispatched_only_once(self):
        digest, _ = propose(self.session, self.snapshot(), "R1", "12", "10", "0")
        apply_proposal(self.session, digest)
        with self.assertRaises(FileExistsError):
            apply_proposal(self.session, digest)
        self.assertEqual(len(self.session.requests), 1)
        request = self.session.requests[0]
        self.assertEqual((request.snapshot_id, request.refdes, request.x), ("2" * 32, "R1", "12"))

    def test_legacy_consumed_proposals_cannot_dispatch_again_after_upgrade(self):
        digest, _ = propose(self.session, self.snapshot(), "R1", "12", "10", "0")
        write_json(self.session.root / f"approval-{digest}.json", {
            "proposal_sha256": digest, "request_id": "3" * 32, "confirmation": f"APPLY {digest}",
        })
        self.assertEqual(load_dispatch_record(self.session, digest)["request_id"], "3" * 32)
        with self.assertRaisesRegex(FileExistsError, "legacy"):
            apply_proposal(self.session, digest)
        self.assertFalse((self.session.root / f"dispatch-{digest}.json").exists())
        self.assertEqual(self.session.requests, [])

    def test_unknown_earlier_dispatch_cannot_be_bypassed_with_another_proposal(self):
        first, _ = propose(self.session, self.snapshot(), "R1", "12", "10", "0")
        apply_proposal(self.session, first)
        second, _ = propose(self.session, self.snapshot(), "R1", "14", "10", "0")
        with self.assertRaisesRegex(SessionError, "earlier placement dispatch is unresolved"):
            apply_proposal(self.session, second)
        self.assertFalse((self.session.root / f"dispatch-{second}.json").exists())
        self.assertEqual(len(self.session.requests), 1)
        request_id = self.session.requests[0].request_id
        write_json(self.session.root / f"{request_id}.receipt.json",
                   Receipt(self.session.nonce, request_id, "applied", "Late result", ()).to_dict())
        apply_proposal(self.session, second)
        self.assertEqual(len(self.session.requests), 2)

    def test_ambiguous_or_mismatched_dispatch_records_do_not_choose_a_winner(self):
        digest = "a" * 64
        path = self.session.root / f"dispatch-{digest}.json"
        path.write_text(json.dumps({"proposal_sha256": "b" * 64, "request_id": "3" * 32}), encoding="utf-8")
        with self.assertRaises(ProtocolError):
            load_dispatch_record(self.session, digest)
        path.write_text(json.dumps({"proposal_sha256": digest, "request_id": "3" * 32}), encoding="utf-8")
        write_json(self.session.root / f"approval-{digest}.json", {
            "proposal_sha256": digest, "request_id": "4" * 32, "confirmation": f"APPLY {digest}",
        })
        with self.assertRaisesRegex(SessionError, "Both legacy and current"):
            load_dispatch_record(self.session, digest)

    def test_history_reports_missing_receipts_and_rejects_wrong_operation_receipts(self):
        digest, _ = propose(self.session, self.snapshot(), "R1", "12", "10", "0")
        apply_proposal(self.session, digest)
        record = load_dispatch_record(self.session, digest)
        result = placement_dispatch_history(self.session)
        self.assertEqual(result[0]["status"], "indeterminate")
        self.assertEqual(result[0]["request"], record["request_id"])
        self.assertEqual(len(self.session.requests), 1)
        self.assertIsNone(read_placement_receipt(self.session, record["request_id"]))
        write_json(self.session.root / f"{record['request_id']}.receipt.json",
                   Receipt(self.session.nonce, record["request_id"], "snapshot", "Not a move", ()).to_dict())
        with self.assertRaisesRegex(ProtocolError, "placement dispatch"):
            placement_dispatch_history(self.session)

    def test_history_rejects_duplicate_request_ids_and_enforces_scan_bound(self):
        for digest in ("a" * 64, "b" * 64):
            write_json(self.session.root / f"dispatch-{digest}.json", {
                "proposal_sha256": digest, "request_id": "3" * 32,
            })
        with self.assertRaisesRegex(ProtocolError, "share a native request"):
            placement_dispatch_history(self.session)
        with patch("orcad_placement_agent.proposals.MAX_DISPATCH_RECORDS", 1):
            with self.assertRaisesRegex(SessionError, "bounded recovery"):
                placement_dispatch_history(self.session)

    def test_receipt_identity_and_mission_binding_are_validated_before_recovery(self):
        digest, request_id = "a" * 64, "3" * 32
        write_json(self.session.root / f"dispatch-{digest}.json", {
            "proposal_sha256": digest, "request_id": request_id,
        })
        path = self.session.root / f"{request_id}.receipt.json"
        for receipt in (
            Receipt("9" * 32, request_id, "applied", "Other session", ()),
            Receipt(self.session.nonce, "4" * 32, "applied", "Other request", ()),
            Receipt(self.session.nonce, request_id, "saved", "Different operation", ()),
        ):
            path.write_text(json.dumps(receipt.to_dict()), encoding="utf-8")
            with self.assertRaises(ProtocolError):
                placement_dispatch_history(self.session)
        path.write_text(json.dumps(Receipt(
            self.session.nonce, request_id, "applied", "Exact result", (),
        ).to_dict()), encoding="utf-8")
        write_json(self.session.root / f"mission-proposal-{digest}.json", {
            "proposal": "b" * 64, "mission": "5" * 32,
        })
        with self.assertRaisesRegex(ProtocolError, "binding was changed"):
            placement_dispatch_history(self.session)


if __name__ == "__main__":
    unittest.main()
