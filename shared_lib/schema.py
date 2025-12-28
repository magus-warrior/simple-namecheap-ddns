"""Shared configuration schemas."""

from typing import List

from pydantic import BaseModel, HttpUrl

try:
    from pydantic import ConfigDict
except ImportError:  # pragma: no cover - Pydantic v1 fallback
    ConfigDict = None  # type: ignore[assignment]


class AgentTarget(BaseModel):
    id: str
    hostname: str
    update_url: HttpUrl
    encrypted_token: str
    interval: int

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")
    else:
        class Config:
            extra = "forbid"


class AgentConfig(BaseModel):
    check_ip_url: HttpUrl
    targets: List[AgentTarget]

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")
    else:
        class Config:
            extra = "forbid"
