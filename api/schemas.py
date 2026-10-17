"""Request bodies for the checkout routes."""
from pydantic import BaseModel, Field


class ScenarioRequest(BaseModel):
    scenario: str


class CustomerRequest(BaseModel):
    customer_name: str = Field(min_length=1, max_length=80)


class AssistAddRequest(BaseModel):
    sku: str = Field(min_length=1, max_length=40)
    object_id: str | None = Field(default=None, max_length=100)


class AssistDismissRequest(BaseModel):
    object_id: str = Field(min_length=1, max_length=100)


class ConfirmationRequest(BaseModel):
    version: int = Field(ge=0)
    idempotency_key: str = Field(min_length=8, max_length=100)
