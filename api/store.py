"""Single-writer local checkout state with durable, idempotent membership changes."""
import json
import uuid
from datetime import timezone
from pathlib import Path
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from .models import Base, Cart, CheckoutEvent, CheckoutSession, PhysicalItem, Receipt

# Must match ProPassScenarios.Classic + Messy in unity/Assets/ProPass/Runtime/ProPassScenario.cs.
SCENARIOS = {"single", "duplicate", "mixed", "occlusion", "remove", "unknown",
             "hands", "shopper", "flatbed", "edge", "stacked", "distractors", "bystander", "hesitate", "parked", "locked", "lumber"}


def new_id():
    return str(uuid.uuid4())


class CheckoutConflict(Exception):
    pass


class Store:
    """Call under the application's one session lock, including confirm and reset."""

    def __init__(self, database_url: str, catalog_path: Path):
        options = {"check_same_thread": False} if database_url.startswith("sqlite") else {}
        self.engine = create_engine(database_url, connect_args=options)
        Base.metadata.create_all(self.engine)
        self.db = sessionmaker(self.engine, expire_on_commit=False)
        catalog = json.loads(catalog_path.read_text())
        self.products = {p["sku"]: p for p in catalog["products"]}
        self.currency = catalog.get("currency", "USD")
        self.session_id = ""
        self.cart_id = ""
        self.reset("single", "Avery Morgan")

    def reset(self, scenario="single", customer_name=None):
        if scenario not in SCENARIOS:
            raise CheckoutConflict("Unknown scenario")
        name = customer_name or (self.snapshot()["session"]["customer_name"] if self.session_id else "Avery Morgan")
        self.session_id, self.cart_id, run_id = new_id(), new_id(), new_id()
        self.resolved = set()   # tracked objects an associate has settled in this session
        with self.db.begin() as db:
            db.add(CheckoutSession(id=self.session_id, customer_name=name, run_id=run_id, scenario=scenario, status="OPEN"))
            db.add(Cart(id=self.cart_id, session_id=self.session_id, status="OPEN", version=0))
        return run_id

    def bind_customer(self, name):
        with self.db.begin() as db:
            cart = db.get(Cart, self.cart_id)
            session = db.get(CheckoutSession, self.session_id)
            if cart.status == "CONFIRMED":
                raise CheckoutConflict("Start a new scenario before changing the demo customer")
            if session.customer_name != name:
                session.customer_name = name
                cart.version += 1
                self._invalidate(cart, session)

    @staticmethod
    def _invalidate(cart, session):
        cart.status = session.status = "OPEN"
        cart.prepared_version = cart.prepared_frame_id = cart.prepared_run_id = None

    def begin_prepare(self):
        with self.db.begin() as db:
            cart = db.get(Cart, self.cart_id)
            session = db.get(CheckoutSession, self.session_id)
            if cart.status == "CONFIRMED":
                raise CheckoutConflict("This cart has already been confirmed")
            cart.status = session.status = "PREPARING"
            return session.run_id

    def abort_prepare(self):
        with self.db.begin() as db:
            cart, session = db.get(Cart, self.cart_id), db.get(CheckoutSession, self.session_id)
            if cart.status in {"PREPARING", "REVIEWING", "ASSIST"}:
                self._invalidate(cart, session)

    def finish_prepare(self, run_id, frame_id, in_progress, assist_open=False):
        """Freeze the cart for review. Items still moving through the lane block it. Items
        that need an associate don't: the scanned part is kept and the cart waits in ASSIST."""
        blocked = False
        with self.db.begin() as db:
            cart, session = db.get(Cart, self.cart_id), db.get(CheckoutSession, self.session_id)
            if session.run_id != run_id or cart.status != "PREPARING":
                raise CheckoutConflict("The checkout session changed during preparation")
            unresolved = db.scalars(select(PhysicalItem).where(PhysicalItem.session_id == self.session_id, PhysicalItem.active.is_(True), PhysicalItem.sku.is_(None))).first()
            if in_progress or unresolved:
                self._invalidate(cart, session)
                blocked = True
            else:
                cart.status = session.status = "ASSIST" if assist_open else "REVIEWING"
                cart.prepared_version, cart.prepared_frame_id, cart.prepared_run_id = cart.version, frame_id, run_id
            version = cart.version
        if blocked:
            raise CheckoutConflict("Items are still moving through the lane. Wait for them to cross, or resume."
                                   if in_progress else "Unresolved product evidence requires review. Resume or run another scenario.")
        return version

    def _associate_event(self, db, session, kind, object_id, sku=None):
        db.add(CheckoutEvent(session_id=self.session_id, run_id=session.run_id, event_id=new_id(), event_type=kind,
                             object_id=object_id, sku=sku, timestamp=0.0,
                             detail=dict(event_id=new_id(), type=kind, object_id=object_id, sku=sku, timestamp=0.0, by="associate")))

    def associate_add(self, sku, resolves=None):
        """An associate adds an item the cameras couldn't settle, or releases a restricted one."""
        if sku not in self.products:
            raise CheckoutConflict("That product is not in the catalog")
        with self.db.begin() as db:
            cart, session = db.get(Cart, self.cart_id), db.get(CheckoutSession, self.session_id)
            if cart.status not in {"ASSIST", "REVIEWING"}:
                raise CheckoutConflict("Review the checkout before an associate adds items")
            object_id = f"associate:{resolves or new_id()}"
            if db.scalar(select(PhysicalItem.id).where(PhysicalItem.session_id == self.session_id, PhysicalItem.object_id == object_id)):
                raise CheckoutConflict("An associate already settled that item")
            db.add(PhysicalItem(id=new_id(), session_id=self.session_id, object_id=object_id, sku=sku, active=True))
            self._associate_event(db, session, "ASSOCIATE_ADDED", object_id, sku)
            cart.version += 1
            cart.prepared_version = cart.version
        if resolves:
            self.resolved.add(resolves)

    def associate_dismiss(self, object_id):
        """An associate confirms a flagged detection is not something to charge."""
        with self.db.begin() as db:
            cart, session = db.get(Cart, self.cart_id), db.get(CheckoutSession, self.session_id)
            if cart.status != "ASSIST":
                raise CheckoutConflict("There is nothing waiting for an associate")
            self._associate_event(db, session, "ASSOCIATE_DISMISSED", object_id)
        self.resolved.add(object_id)

    def finish_assist(self):
        """Every flagged item is settled: the cart moves on to customer confirmation."""
        with self.db.begin() as db:
            cart, session = db.get(Cart, self.cart_id), db.get(CheckoutSession, self.session_id)
            if cart.status == "ASSIST":
                cart.status = session.status = "REVIEWING"
                cart.prepared_version = cart.version

    def apply_result(self, result):
        with self.db.begin() as db:
            session, cart = db.get(CheckoutSession, self.session_id), db.get(Cart, self.cart_id)
            if result.get("run_id") != session.run_id or cart.status == "CONFIRMED":
                return False
            for event in result.get("events", []):
                event_id = str(event.get("event_id", ""))
                if not event_id:
                    raise ValueError("Vision event must have a stable event_id")
                exists = db.scalar(select(CheckoutEvent.id).where(CheckoutEvent.run_id == session.run_id, CheckoutEvent.event_id == event_id))
                if exists is not None:
                    continue
                kind, oid, sku = event.get("type", ""), event.get("object_id"), event.get("sku")
                if sku is not None and sku not in self.products:
                    raise ValueError("Vision emitted a SKU outside the demo catalog")
                db.add(CheckoutEvent(session_id=self.session_id, run_id=session.run_id, event_id=event_id, event_type=kind, object_id=str(oid) if oid is not None else None, sku=sku, timestamp=float(event.get("timestamp", result.get("timestamp", 0))), detail=event))
                if kind == "REVIEW_REQUIRED" and cart.status == "REVIEWING":
                    self._invalidate(cart, session)
                    cart.version += 1
                if kind not in {"ITEM_ADDED", "ITEM_REMOVED", "SKU_RESOLVED"} or oid is None:
                    continue
                item = db.scalar(select(PhysicalItem).where(PhysicalItem.session_id == self.session_id, PhysicalItem.object_id == str(oid)))
                if item is None:
                    item = PhysicalItem(id=new_id(), session_id=self.session_id, object_id=str(oid), sku=sku, active=False)
                    db.add(item)
                before = (item.active, item.sku)
                if kind == "ITEM_ADDED":
                    item.active = True
                    if sku is not None:
                        item.sku = sku
                elif kind == "ITEM_REMOVED":
                    item.active = False
                elif sku is not None:
                    item.sku = sku
                if before != (item.active, item.sku):
                    if cart.status == "REVIEWING":
                        self._invalidate(cart, session)
                    cart.version += 1
            return True

    def _lines(self, db):
        counts, by_associate = {}, {}
        for item in db.scalars(select(PhysicalItem).where(PhysicalItem.session_id == self.session_id, PhysicalItem.active.is_(True))):
            if item.sku:
                counts[item.sku] = counts.get(item.sku, 0) + 1
                by_associate[item.sku] = by_associate.get(item.sku, 0) + item.object_id.startswith("associate:")
        return [dict(sku=sku, name=self.products[sku]["name"], quantity=qty, unit_price=self.products[sku]["price"],
                     line_total=round(self.products[sku]["price"] * qty, 2), added_by_associate=by_associate[sku])
                for sku, qty in sorted(counts.items())]

    @staticmethod
    def _receipt(receipt):
        created = receipt.created_at
        if created.tzinfo is None:
            created = created.replace(tzinfo=timezone.utc)
        return dict(id=receipt.id, cart_id=receipt.cart_id, customer_name=receipt.customer_name, version=receipt.confirmed_version, items=receipt.lines, total=receipt.total, created_at=created.isoformat(), simulated=True)

    def confirm(self, version, idempotency_key, current_run_id, review_required=False):
        with self.db.begin() as db:
            cart = db.scalar(select(Cart).where(Cart.id == self.cart_id).with_for_update())
            session = db.get(CheckoutSession, self.session_id)
            existing = db.scalar(select(Receipt).where(Receipt.cart_id == cart.id))
            if existing:
                if existing.idempotency_key != idempotency_key or existing.confirmed_version != version:
                    raise CheckoutConflict("This cart was confirmed by a different request")
                return self._receipt(existing)
            if cart.status != "REVIEWING" or cart.version != version or cart.prepared_version != version or cart.prepared_run_id != current_run_id or session.run_id != current_run_id or review_required:
                raise CheckoutConflict("Cart evidence changed. Prepare the current cart again.")
            lines = self._lines(db)
            if not lines:
                raise CheckoutConflict("There are no recognized products to confirm")
            receipt = Receipt(id=new_id(), cart_id=cart.id, idempotency_key=idempotency_key, confirmed_version=version, customer_name=session.customer_name, lines=lines, total=round(sum(i["line_total"] for i in lines), 2))
            db.add(receipt)
            db.flush()
            cart.status = session.status = "CONFIRMED"
            return self._receipt(receipt)

    def snapshot(self):
        with self.db() as db:
            session, cart = db.get(CheckoutSession, self.session_id), db.get(Cart, self.cart_id)
            lines = self._lines(db)
            receipt = db.scalar(select(Receipt).where(Receipt.cart_id == cart.id))
            events = db.scalars(select(CheckoutEvent).where(CheckoutEvent.session_id == self.session_id).order_by(CheckoutEvent.id.desc()).limit(60)).all()
            return dict(session=dict(id=session.id, customer_name=session.customer_name, status=session.status, run_id=session.run_id), cart=dict(id=cart.id, version=cart.version, status=cart.status, prepared_version=cart.prepared_version, prepared_frame_id=cart.prepared_frame_id, items=lines, total=round(sum(i["line_total"] for i in lines), 2), currency=self.currency), simulator=dict(scenario=session.scenario, run_id=session.run_id), events=[dict(**e.detail, sequence=e.id) for e in events], receipt=self._receipt(receipt) if receipt else None)
