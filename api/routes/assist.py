"""Associate hand-off: add an item, release a restricted one, or dismiss a flagged detection."""
from fastapi import APIRouter, HTTPException

from ..schemas import AssistAddRequest, AssistDismissRequest
from ..store import CheckoutConflict


def router(runtime):
    api = APIRouter()

    async def associate(action):
        async with runtime.lock:
            try:
                action()
                if not runtime.assist_state()[1]:
                    runtime.store.finish_assist()
            except CheckoutConflict as exc:
                raise HTTPException(409, str(exc)) from exc
            state = runtime.snapshot()
        await runtime.publish()
        return state

    @api.post("/api/assist/add")
    async def assist_add(body: AssistAddRequest):
        """An associate adds an item (optionally settling a flagged object) or releases a restricted one."""
        return await associate(lambda: runtime.store.associate_add(body.sku, body.object_id))

    @api.post("/api/assist/dismiss")
    async def assist_dismiss(body: AssistDismissRequest):
        """An associate confirms a flagged detection is nothing to charge."""
        return await associate(lambda: runtime.store.associate_dismiss(body.object_id))

    return api
