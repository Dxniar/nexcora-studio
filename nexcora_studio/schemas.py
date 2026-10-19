from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class StrictBody(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class TelegramLogin(StrictBody):
    init_data: str = Field(min_length=1, max_length=16_384)


class SaveDraft(StrictBody):
    expected_version: int = Field(ge=0)
    fields: dict[str, str | None]


class SubmitDraft(StrictBody):
    draft_id: str = Field(min_length=1, max_length=64)
    expected_version: int = Field(ge=0)
    attachments_version: int = Field(ge=0)


class Action(StrictBody):
    expected_version: int = Field(ge=0)
    proposal_version: int | None = Field(default=None, ge=1)
    delivery_version: int | None = Field(default=None, ge=1)
    comment: str | None = Field(default=None, max_length=2000)
    reason: str | None = Field(default=None, max_length=1000)
    scope: str | None = Field(default=None, max_length=3000)
    result: str | None = Field(default=None, max_length=2000)
    price_minor: int | None = Field(default=None, ge=1, le=10**12)
    currency: str | None = Field(default=None, max_length=3)
    deadline: str | None = Field(default=None, max_length=10)
    revision_terms: str | None = Field(default=None, max_length=1000)
    description: str | None = Field(default=None, max_length=2000)
    url: str | None = Field(default=None, max_length=2000)


class Preferences(StrictBody):
    notifications_enabled: bool
    expected_version: int = Field(ge=0)


class LanguagePreference(StrictBody):
    language_code: Literal['ru', 'en', 'kk']


class DeleteData(StrictBody):
    confirmation_token: str = Field(min_length=20, max_length=128)
