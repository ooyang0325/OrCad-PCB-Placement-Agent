"""Exact, inspectable proposals and one-use dispatch records."""

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
import json
import re
import uuid

from .protocol import (
    ProtocolError, Receipt, Request, canonical_digest, decimal_text, identifier, number,
)
from .session import Session, SessionError, write_json


MAX_DISPATCH_RECORDS = 4096


@dataclass(frozen=True)
class Component:
    refdes: str
    package: str
    x: Decimal
    y: Decimal
    angle: Decimal
    mirrored: bool
    fixed: bool
    placed: bool

    @classmethod
    def from_record(cls, record: tuple[str, ...]) -> "Component":
        if len(record) != 9 or record[0] != "component":
            raise ProtocolError("Invalid component record.")
        if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,30}", record[1]) is None:
            raise ProtocolError("Unsupported reference designator.")
        if any(value not in ("0", "1") for value in record[6:9]):
            raise ProtocolError("Invalid component state flags.")
        return cls(
            record[1], record[2], *(number(value) for value in record[3:6]),
            *(value == "1" for value in record[6:9]),
        )


def check_snapshot(receipt: Receipt) -> dict[str, Component]:
    if receipt.status != "snapshot":
        raise ProtocolError("A successful read-only snapshot is required.")
    if any(row[0] == "model" and row[1] != "managed-board-v1" for row in receipt.records):
        raise ProtocolError("A library-setup or unknown model cannot authorize placement or saving.")
    identifier(receipt.one("snapshot")[1])
    receipt.one("board")
    receipt.one("version")
    receipt.scene
    units = receipt.one("units")
    if units[1] != "millimeters" or number(units[3]) <= 0:
        raise ProtocolError("The initial fixture requires known millimeter/DBU units.")
    if not units[2].isdigit() or not 0 <= int(units[2]) <= 9:
        raise ProtocolError("Invalid board accuracy.")
    components: dict[str, Component] = {}
    for row in receipt.records:
        if row[0] == "component":
            item = Component.from_record(row)
            if item.refdes in components:
                raise ProtocolError("Duplicate reference designators in snapshot.")
            components[item.refdes] = item
    if not components:
        raise ProtocolError("No components in snapshot.")
    return components


def propose(
    session: Session, snapshot: Receipt, refdes: str, x: str, y: str, angle: str,
) -> tuple[str, dict[str, object]]:
    components = check_snapshot(snapshot)
    if snapshot.nonce != session.nonce:
        raise ProtocolError("Snapshot belongs to a different session.")
    if refdes not in components:
        raise ProtocolError("Target component is missing.")
    component = components[refdes]
    managed = any(row == ("model", "managed-board-v1") for row in snapshot.records)
    board = None
    if managed:
        from .board import from_receipt

        board = from_receipt(snapshot)
    if component.fixed or component.mirrored or (not component.placed and not managed):
        raise ProtocolError("Target must be unfixed/top-side; initial placement needs a complete managed-board snapshot.")
    scale = number(snapshot.one("units")[3])
    target_x = (number(x) * scale).to_integral_value(rounding=ROUND_HALF_UP) / scale
    target_y = (number(y) * scale).to_integral_value(rounding=ROUND_HALF_UP) / scale
    target_angle = number(angle)
    if target_angle not in (0, 90, 180, 270):
        raise ProtocolError("The initial fixture supports only 0/90/180/270 degree targets.")
    if component.placed and (target_x, target_y, target_angle) == (component.x, component.y, component.angle):
        raise ProtocolError("Proposal is a no-op.")
    if board is not None and "outline_boundary" in board:
        from .boundaries import board_boundaries, footprint_box

        target = next(part for part in board["components"] if part["refdes"] == refdes)
        box = footprint_box(tuple(number(value) for value in target["bounds"]),
                            target_x, target_y, decimal_text(target_angle))
        if not all(boundary.contains_box(box) for boundary in board_boundaries(board)):
            raise ProtocolError("Target footprint crosses the native outline/keepin contour or approximation margin.")
    if board is not None and "design_policy" in board:
        from .boundaries import footprint_box
        from .room_geometry import check_target_room

        target = next(part for part in board["components"] if part["refdes"] == refdes)
        box = footprint_box(tuple(number(value) for value in target["bounds"]),
                            target_x, target_y, decimal_text(target_angle))
        check_target_room(board, refdes, box)
    proposal: dict[str, object] = {
        "schema_version": 1,
        "nonce": session.nonce,
        "snapshot_id": snapshot.one("snapshot")[1],
        "scene_digest": snapshot.scene_digest,
        "snapshot": snapshot.to_dict(),
        "refdes": refdes,
        "x": decimal_text(target_x),
        "y": decimal_text(target_y),
        "angle": decimal_text(target_angle),
        "units": "millimeters",
        "pivot": "component-origin",
    }
    digest = canonical_digest(proposal)
    path = session.root / f"proposal-{digest}.json"
    if path.exists():
        if json.loads(path.read_text(encoding="utf-8")) != proposal:
            raise SessionError("Existing proposal content does not match its identity.")
    else:
        write_json(path, proposal)
    return digest, proposal


def load_proposal(session: Session, digest: str) -> dict[str, object]:
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ProtocolError("Expected a SHA256 proposal identifier.")
    proposal = session._read_json(f"proposal-{digest}.json")
    expected = {
        "schema_version", "nonce", "snapshot_id", "scene_digest", "snapshot",
        "refdes", "x", "y", "angle", "units", "pivot",
    }
    if set(proposal) != expected or canonical_digest(proposal) != digest:
        raise ProtocolError("The proposal was altered or has an unsupported schema.")
    if (
        proposal["schema_version"] != 1 or proposal["nonce"] != session.nonce
        or proposal["units"] != "millimeters" or proposal["pivot"] != "component-origin"
    ):
        raise ProtocolError("The proposal belongs to another session or operation.")
    identifier(proposal["snapshot_id"])
    for key in ("x", "y", "angle"):
        number(proposal[key])
    if number(proposal["angle"]) not in (0, 90, 180, 270):
        raise ProtocolError("Unsupported target rotation.")
    return proposal


def proposal_summary(proposal: dict[str, object]) -> str:
    snapshot = proposal["snapshot"]
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("records"), list):
        raise ProtocolError("Proposal lacks its reviewed snapshot.")
    components = [
        Component.from_record(tuple(row))
        for row in snapshot["records"]
        if row[0] == "component" and row[1] == proposal["refdes"]
    ]
    if len(components) != 1:
        raise ProtocolError("Reviewed component is missing or ambiguous.")
    before = components[0]
    source = f"({before.x}, {before.y}) mm, {before.angle} degrees" if before.placed else "UNPLACED"
    return (
        f"{before.refdes}: {source} -> "
        f"({proposal['x']}, {proposal['y']}) mm, {proposal['angle']} degrees; "
        "pivot: component origin; top side unchanged; memory only."
    )


def apply_proposal(session: Session, digest: str) -> Receipt:
    proposal = load_proposal(session, digest)
    if (session.root / f"approval-{digest}.json").exists():
        raise FileExistsError("This proposal was already consumed by a legacy approval; do not replay it.")
    if (session.root / f"dispatch-{digest}.json").exists():
        raise FileExistsError("This proposal was already consumed; do not replay it.")
    if any(item["status"] == "indeterminate" for item in placement_dispatch_history(session)):
        raise SessionError("An earlier placement dispatch is unresolved; reconcile it before applying a different proposal.")
    request_id = uuid.uuid4().hex
    write_json(session.root / f"dispatch-{digest}.json", {
        "proposal_sha256": digest, "request_id": request_id,
    })
    # Creating the dispatch record consumes this proposal even if delivery becomes
    # uncertain. A second invocation cannot replay the same mutation.
    request = Request(
        session.nonce, request_id, "apply", proposal["snapshot_id"],
        proposal["refdes"], proposal["x"], proposal["y"], proposal["angle"],
    )
    return session.exchange(request)


def load_dispatch_record(session: Session, digest: str) -> dict[str, object] | None:
    if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise ProtocolError("Expected an exact proposal identifier for dispatch recovery.")
    paths = [path for path in (
        session.root / f"dispatch-{digest}.json", session.root / f"approval-{digest}.json",
    ) if path.exists()]
    if not paths:
        return None
    if len(paths) != 1:
        raise SessionError("Both legacy and current dispatch records exist; resolve the ambiguous outcome without replay.")
    path = paths[0]
    record = session._read_json(path.name)
    legacy = path.name.startswith("approval-")
    expected = {"proposal_sha256", "request_id"} | ({"confirmation"} if legacy else set())
    if (not isinstance(record, dict) or set(record) != expected
            or record["proposal_sha256"] != digest
            or (legacy and record["confirmation"] != f"APPLY {digest}")):
        raise ProtocolError("Dispatch record does not match its exact proposal.")
    identifier(record["request_id"])
    return record


def read_placement_receipt(session: Session, request_id: str) -> Receipt | None:
    identifier(request_id)
    path = session.root / f"{request_id}.receipt.json"
    if not path.exists():
        return None
    receipt = Receipt.from_dict(session._read_json(path.name))
    if (receipt.nonce != session.nonce or receipt.request_id != request_id
            or receipt.status not in {"applied", "rejected", "rolled_back", "indeterminate"}):
        raise ProtocolError("Recorded outcome does not match this placement dispatch.")
    return receipt


def placement_dispatch_history(session: Session) -> list[dict[str, object]]:
    """Read bounded immutable dispatch evidence; never poll, replay or clear requests."""
    digests = set()
    for prefix in ("dispatch-", "approval-"):
        for path in session.root.glob(prefix + "*.json"):
            digest = path.name[len(prefix):-5]
            if re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise ProtocolError("Malformed placement dispatch artifact name.")
            digests.add(digest)
            if len(digests) > MAX_DISPATCH_RECORDS:
                raise SessionError("Placement dispatch history exceeds the bounded recovery inventory.")
    outcomes = []
    requests = set()
    for digest in sorted(digests):
        record = load_dispatch_record(session, digest)
        if record is None:
            raise SessionError("A dispatch record disappeared during recovery.")
        if record["request_id"] in requests:
            raise ProtocolError("Different placement proposals share a native request identifier.")
        requests.add(record["request_id"])
        receipt = read_placement_receipt(session, record["request_id"])
        mission = None
        path = session.root / f"mission-proposal-{digest}.json"
        if path.exists():
            binding = session._read_json(path.name)
            if (not isinstance(binding, dict) or set(binding) != {"mission", "proposal"}
                    or binding["proposal"] != digest):
                raise ProtocolError("Mission-to-proposal binding was changed.")
            mission = identifier(binding["mission"])
        outcomes.append({
            "proposal": digest, "request": record["request_id"], "mission": mission,
            "status": receipt.status if receipt is not None else "indeterminate",
            "message": receipt.message if receipt is not None else
                       "Dispatch consumed without a terminal receipt. Use exact execution status; do not create a replacement.",
        })
    return outcomes
