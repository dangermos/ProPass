"""Checkout session: pick a scenario, bind a customer, prepare, resume and confirm the cart."""
import asyncio

from fastapi import APIRouter, HTTPException, Response

from ..schemas import ConfirmationRequest, CustomerRequest, ScenarioRequest
from ..store import SCENARIOS, CheckoutConflict
from .replay import start_replay


def router(runtime):
    api = APIRouter()

    @api.post("/api/scenario")
    async def scenario(body: ScenarioRequest):
        if body.scenario not in SCENARIOS:
            raise HTTPException(422, "Unknown checkout scenario")
        runtime.stop_replay()
        return await runtime.reset_run(body.scenario)

    @api.post("/api/cart/reset")
    async def reset():
        async with runtime.lock:
            scenario_name = runtime.store.snapshot()["simulator"]["scenario"]
        if runtime.replay_run is not None:
            return await start_replay(runtime, scenario_name)
        return await runtime.reset_run(scenario_name)

    @api.post("/api/session")
    async def session(body: CustomerRequest):
        if not body.customer_name.strip():
            raise HTTPException(422, "A demo customer name is required")
        async with runtime.lock:
            try:
                runtime.store.bind_customer(body.customer_name.strip())
            except CheckoutConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            runtime.paused = False
            state = runtime.snapshot()
        await runtime.publish()
        return state

    @api.post("/api/cart/resume")
    async def resume():
        async with runtime.lock:
            if runtime.store.snapshot()["cart"]["status"] == "CONFIRMED":
                raise HTTPException(409, "Start a new scenario after confirmation")
            runtime.store.abort_prepare()
            runtime.paused = False
            state = runtime.snapshot()
        await runtime.publish()
        return state

    @api.post("/api/cart/prepare")
    async def prepare():
        async with runtime.lock:
            if not runtime.frame and runtime.pending_group is None and runtime.queue.empty() and not runtime.loading:
                raise HTTPException(409, "Wait for the first accepted Unity frame")
            try:
                run_id = runtime.store.begin_prepare()
            except CheckoutConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            runtime.paused = True
            runtime.flush_pending()
        await runtime.publish()
        try:
            await asyncio.wait_for(runtime.queue.join(), timeout=30)
        except TimeoutError:
            return Response(status_code=202, content='{"pending":true,"message":"Draining accepted camera frames"}', media_type="application/json")
        async with runtime.lock:
            conflict = None
            try:
                if runtime.store.snapshot()["session"]["run_id"] != run_id:
                    raise CheckoutConflict("The checkout session changed during preparation")
                if runtime.error:
                    runtime.store.abort_prepare()
                    raise CheckoutConflict(runtime.error)
                if runtime.frame is None:
                    runtime.store.abort_prepare()
                    raise CheckoutConflict("No camera frame was processed during preparation")
                if not runtime.vision_status().get("ready", False):
                    runtime.store.abort_prepare()
                    raise CheckoutConflict("The vision checkpoint is not ready")
                in_progress, assist = runtime.assist_state()
                runtime.store.finish_prepare(run_id, runtime.frame["frame_id"], bool(in_progress), bool(assist))
            except CheckoutConflict as exc:
                conflict = str(exc)
            state = runtime.snapshot()
        await runtime.publish()
        if conflict:
            raise HTTPException(409, conflict)
        return state

    @api.post("/api/cart/confirm")
    async def confirm(body: ConfirmationRequest):
        async with runtime.lock:
            state = runtime.store.snapshot()
            try:
                in_progress, assist = runtime.assist_state()
                receipt = runtime.store.confirm(body.version, body.idempotency_key, state["session"]["run_id"], bool(in_progress or assist or runtime.error))
            except CheckoutConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            runtime.paused = True
        await runtime.publish()
        return receipt

    return api
