"""YAML deep-merge for /etc/spark-modem-watchdog/conf.d/*.yaml.

Files are merged in lexical filename order — `00-base.yaml` is loaded first,
then `99-local.yaml` overlays it. Lists REPLACE (do not extend); leaf scalars
are overridden by the latest layer.

The carrier-table-validator (spark_modem.wire.CarrierTable) is what catches
the YAML "Norway problem" (`country: NO` parses as bool); the merger here
is YAML-shape-agnostic.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively merge `override` into `base`.

    - Both dict at the same path → recurse.
    - Otherwise → override wins (including type changes; including lists).
    Returns a new dict; inputs are not mutated.
    """
    out: dict[str, Any] = dict(base)
    for k, v in override.items():
        if k in out and isinstance(out[k], dict) and isinstance(v, dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_yaml_layer(conf_d_dir: Path | str) -> dict[str, Any]:
    """Read every *.yaml file under conf_d_dir in lexical order; deep-merge."""
    d = Path(conf_d_dir)
    if not d.is_dir():
        return {}
    result: dict[str, Any] = {}
    for f in sorted(d.iterdir()):
        if not f.is_file() or f.suffix not in (".yaml", ".yml"):
            continue
        try:
            content = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        except (OSError, yaml.YAMLError):
            # FR-63: invalid input is logged error, not crash. Plan 06 doesn't
            # have access to the event_logger from this module to avoid an
            # import cycle; we surface the error by skipping the file.
            # Phase 3 wires a structured "config_invalid" event via the daemon
            # boot path. For Phase 1, skipping is the right default.
            continue
        if isinstance(content, dict):
            result = deep_merge(result, content)
    return result
