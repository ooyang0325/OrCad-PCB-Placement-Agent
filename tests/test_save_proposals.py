import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from orcad_placement_agent.protocol import ProtocolError, Receipt
from orcad_placement_agent.save_proposals import prepare_save, apply_save, load_save, save_status
from orcad_placement_agent.session import SessionError
from orcad_placement_agent.transport import IndeterminateDelivery
from tests.test_board import managed_snapshot


class SaveProposalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)

        class FakeSession:
            nonce = "1" * 32

            def __init__(self, root):
                self.root = root
                self.calls = []

            def _read_json(self, name):
                return json.loads((self.root / name).read_text())

            def exchange(self, request):
                self.calls.append(request)
                path = self.root / request.destination
                path.write_bytes(b"Original simulated saved board")
                receipt = Receipt(self.nonce, request.request_id, "saved", "Fake saved",
                                  (*managed_snapshot().records, ("saved", str(path))))
                (self.root / f"{request.request_id}.receipt.json").write_text(json.dumps(receipt.to_dict()))
                return receipt

        self.session = FakeSession(Path(self.temp.name))

    def test_prepare_is_nonmutating_and_save_dispatches_once_without_confirmation(self):
        digest, value = prepare_save(self.session, managed_snapshot())
        self.assertEqual(load_save(self.session, digest), value)
        self.assertEqual(save_status(self.session, digest)["status"], "not_dispatched")
        self.assertEqual(self.session.calls, [])
        receipt = apply_save(self.session, digest)
        self.assertEqual(receipt.status, "saved")
        self.assertEqual(self.session.calls[0].operation, "save")
        status = save_status(self.session, digest)
        self.assertTrue(status["artifact_available"])
        self.assertFalse(status["reopened"])
        record = self.session._read_json(f"save-dispatch-{digest}.json")
        self.assertEqual(set(record), {"proposal", "request_id"})
        with self.assertRaises((FileExistsError, SessionError)):
            apply_save(self.session, digest)
        self.assertEqual(len(self.session.calls), 1)

    def test_existing_revision_is_never_overwritten(self):
        digest, value = prepare_save(self.session, managed_snapshot())
        path = self.session.root / value["destination"]
        path.write_bytes(b"Keep this existing revision")
        with self.assertRaises(SessionError):
            apply_save(self.session, digest)
        self.assertEqual(path.read_bytes(), b"Keep this existing revision")
        self.assertEqual(self.session.calls, [])

    def test_timeout_consumes_dispatch_without_replay(self):
        digest, _ = prepare_save(self.session, managed_snapshot())
        with patch.object(self.session, "exchange", side_effect=IndeterminateDelivery("No receipt")) as exchange:
            with self.assertRaises(IndeterminateDelivery):
                apply_save(self.session, digest)
            self.assertEqual(save_status(self.session, digest)["status"], "indeterminate")
            with self.assertRaises(SessionError):
                apply_save(self.session, digest)
            exchange.assert_called_once()

    def test_legacy_record_blocks_replay_and_preserves_status(self):
        digest, _ = prepare_save(self.session, managed_snapshot())
        receipt = apply_save(self.session, digest)
        (self.session.root / f"save-dispatch-{digest}.json").unlink()
        path = self.session.root / f"save-approval-{digest}.json"
        path.write_text(json.dumps({"proposal": digest, "request_id": receipt.request_id,
                                    "confirmation": f"SAVE {digest}"}))
        self.assertEqual(save_status(self.session, digest)["status"], "saved")
        with self.assertRaises(SessionError):
            apply_save(self.session, digest)
        self.assertEqual(len(self.session.calls), 1)

    def test_modified_proposal_never_dispatches(self):
        digest, value = prepare_save(self.session, managed_snapshot())
        value["destination"] = "source.brd"
        (self.session.root / f"save-proposal-{digest}.json").write_text(json.dumps(value))
        with self.assertRaises(ProtocolError):
            apply_save(self.session, digest)
        self.assertEqual(self.session.calls, [])


if __name__ == "__main__":
    unittest.main()
