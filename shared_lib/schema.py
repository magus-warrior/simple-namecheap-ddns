"""Shared configuration schemas."""

from typing import List, Optional
import ipaddress

from pydantic import BaseModel, HttpUrl

try:
    from pydantic import ConfigDict, field_validator
except ImportError:  # pragma: no cover - Pydantic v1 fallback
    ConfigDict = None  # type: ignore[assignment]
    from pydantic import validator  # type: ignore[no-redef]
    field_validator = None  # type: ignore[assignment]


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
    manual_ip_enabled: bool = False
    manual_ip_address: Optional[str] = None

    if field_validator is not None:

        @field_validator("manual_ip_address")
        @classmethod
        def _validate_manual_ip_address(
            cls,
            value: Optional[str],
        ) -> Optional[str]:
            if not value:
                return None
            ipaddress.ip_address(value)
            return value

    else:

        @validator("manual_ip_address")
        def _validate_manual_ip_address(  # type: ignore[no-redef]
            cls,
            value: Optional[str],
        ) -> Optional[str]:
            if not value:
                return None
            ipaddress.ip_address(value)
            return value

    if ConfigDict is not None:
        model_config = ConfigDict(extra="forbid")
    else:
        class Config:
            extra = "forbid"
