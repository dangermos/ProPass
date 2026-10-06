"""Associate hand-off: the scanned cart is kept, an associate settles the rest, then checkout completes."""
from fastapi.testclient import TestClient

from api.app import create_app
from tests.test_api_checkout import event, post_frame, wait_frame


class AssistVision:
    """Stub engine: one scanned drill kit in the cart, plus whatever needs an associate."""

    def __init__(self, assist=(), in_progress=0):
        self.assist, self.in_progress = list(assist), in_progress

    def reset(self, run_id):
        pass

    def status(self):
        return {"ready": True, "mode": "deterministic_test_double"}

    def process_frame(self, image, frame_id, timestamp, run_id):
        member = dict(object_id="obj-1", sku="PEX-001", membership=True, rating="verified", sku_source="barcode")
        return dict(run_id=run_id, frame_id=frame_id, timestamp=timestamp, detections=[], objects=[member],
                    events=[event("crossing", oid="obj-1", sku="PEX-001")], metrics={},
                    review_required=bool(self.assist or self.in_progress), assist=self.assist, in_progress=self.in_progress)


def client_with(tmp_path, vision):
    return TestClient(create_app(f"sqlite:///{tmp_path / 'assist.db'}", lambda: vision, camera_ids=["lane"]))


def start(client):
    run = client.get("/api/simulator/control").json()["run_id"]
    assert post_frame(client, run).status_code == 200
    wait_frame(client, 1)
    return client.post("/api/cart/prepare")


UNSCANNED = dict(object_id="obj-2", sku=None, reason="Checkout crossing lacks accepted SKU evidence", restricted=False)
LOCKED = dict(object_id="obj-3", sku="PEX-002", reason="Restricted item: an associate must release it", restricted=True)


def test_unscanned_item_hands_off_to_an_associate_and_keeps_the_scanned_cart(tmp_path):
    with client_with(tmp_path, AssistVision([UNSCANNED])) as client:
        state = start(client).json()
        assert state["cart"]["status"] == "ASSIST"
        assert [line["sku"] for line in state["cart"]["items"]] == ["PEX-001"]
        assert state["cart"]["items"][0]["rating"] == "verified"
        assert [a["object_id"] for a in state["assist"]] == ["obj-2"]
        # Confirmation is impossible until the associate settles it.
        blocked = client.post("/api/cart/confirm", json={"version": state["cart"]["version"], "idempotency_key": "attempt-0001"})
        assert blocked.status_code == 409


def test_associate_adds_the_missing_item_then_the_customer_confirms(tmp_path):
    with client_with(tmp_path, AssistVision([UNSCANNED])) as client:
        start(client)
        state = client.post("/api/assist/add", json={"sku": "PEX-003", "object_id": "obj-2"}).json()
        assert state["assist"] == [] and state["cart"]["status"] == "REVIEWING"
        lines = {line["sku"]: line for line in state["cart"]["items"]}
        assert lines["PEX-003"]["rating"] == "associate" and lines["PEX-003"]["added_by_associate"] == 1
        assert lines["PEX-001"]["added_by_associate"] == 0
        receipt = client.post("/api/cart/confirm", json={"version": state["cart"]["version"], "idempotency_key": "attempt-0002"})
        assert receipt.status_code == 200
        assert {line["sku"] for line in receipt.json()["items"]} == {"PEX-001", "PEX-003"}
        assert any(e["type"] == "ASSOCIATE_ADDED" for e in client.get("/api/snapshot").json()["events"])


def test_associate_can_dismiss_a_false_detection(tmp_path):
    with client_with(tmp_path, AssistVision([UNSCANNED])) as client:
        start(client)
        state = client.post("/api/assist/dismiss", json={"object_id": "obj-2"}).json()
        assert state["assist"] == [] and state["cart"]["status"] == "REVIEWING"
        assert [line["sku"] for line in state["cart"]["items"]] == ["PEX-001"]


def test_restricted_item_waits_for_an_associate_to_release_it(tmp_path):
    with client_with(tmp_path, AssistVision([LOCKED, UNSCANNED])) as client:
        state = start(client).json()
        assert {a["object_id"] for a in state["assist"]} == {"obj-2", "obj-3"}
        state = client.post("/api/assist/add", json={"sku": "PEX-002", "object_id": "obj-3"}).json()
        assert state["cart"]["status"] == "ASSIST"          # one item still open
        state = client.post("/api/assist/dismiss", json={"object_id": "obj-2"}).json()
        assert state["cart"]["status"] == "REVIEWING"
        assert client.post("/api/assist/add", json={"sku": "PEX-002", "object_id": "obj-3"}).status_code == 409   # not twice


def test_items_still_moving_block_review_instead_of_calling_an_associate(tmp_path):
    with client_with(tmp_path, AssistVision(in_progress=1)) as client:
        response = start(client)
        assert response.status_code == 409 and "still moving" in response.json()["detail"]
        assert client.get("/api/snapshot").json()["cart"]["status"] == "OPEN"


def test_associate_cannot_add_before_review_or_an_unknown_product(tmp_path):
    with client_with(tmp_path, AssistVision([UNSCANNED])) as client:
        assert client.post("/api/assist/add", json={"sku": "PEX-003"}).status_code == 409
        start(client)
        assert client.post("/api/assist/add", json={"sku": "NOT-A-SKU"}).status_code == 409
