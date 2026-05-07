"""tenant_id 검증."""

from __future__ import annotations

import re

_TENANT_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")


def validate_tenant_id(tenant_id: str) -> str:
    if not _TENANT_RE.fullmatch(tenant_id):
        raise ValueError(
            "tenant_id must be 1-64 chars of [a-zA-Z0-9_-]",
        )
    return tenant_id


def assert_tenant_allowed(tenant_id: str, default_tenant_id: str) -> None:
    """단일 테넌트 모드: 기본 테넌트만 허용 (추후 멀티 테넌트 확장)."""
    validate_tenant_id(tenant_id)
    if tenant_id != default_tenant_id:
        raise PermissionError(f"tenant_id must be {default_tenant_id!r} in single-tenant mode")
