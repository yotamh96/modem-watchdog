"""Field-level reload markers — annotate Settings fields with reload semantics.

Phase 3's SIGHUP listener (FR-54) reads these to decide:
  RELOAD_DATA    → re-apply on SIGHUP without daemon restart.
  RELOAD_RESTART → log a structured 'restart_required' event and refuse
                   to apply mid-flight (changing state root or socket
                   paths is a topology change, not a config tweak).
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel
from pydantic.fields import FieldInfo

RELOAD_DATA: dict[str, Any] = {"reload": "data"}
RELOAD_RESTART: dict[str, Any] = {"reload": "restart"}


def reload_class(field_info: FieldInfo) -> str | None:
    extra = field_info.json_schema_extra
    if isinstance(extra, dict):
        value = extra.get("reload")
        if isinstance(value, str):
            return value
    return None


def restart_required_fields(model_cls: type[BaseModel]) -> frozenset[str]:
    """Return the set of field names tagged with RELOAD_RESTART on model_cls."""
    out: set[str] = set()
    for name, info in model_cls.model_fields.items():
        if reload_class(info) == "restart":
            out.add(name)
    return frozenset(out)


def data_reloadable_fields(model_cls: type[BaseModel]) -> frozenset[str]:
    """Return the set of field names tagged with RELOAD_DATA on model_cls."""
    out: set[str] = set()
    for name, info in model_cls.model_fields.items():
        if reload_class(info) == "data":
            out.add(name)
    return frozenset(out)
