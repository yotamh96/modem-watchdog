"""YAML deep-merge for /etc/spark-modem-watchdog/conf.d/*.yaml.

Files are merged in lexical filename order — `00-base.yaml` is loaded first,
then `99-local.yaml` overlays it. Lists REPLACE (do not extend); leaf scalars
are overridden by the latest layer.

The carrier-table-validator (spark_modem.wire.CarrierTable) is what catches
the YAML "Norway problem" (`country: NO` parses as bool); the merger here
is YAML-shape-agnostic.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

_logger = logging.getLogger(__name__)


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
        except (OSError, yaml.YAMLError) as e:
            # FR-63: invalid input is a logged error, not a crash. Phase 3 will
            # wire a structured "config_invalid" event via the daemon boot path.
            # For now, log to the stdlib logger so the failure is always visible
            # in systemd journal and on the operator's terminal.
            _logger.warning(
                "spark_modem.config: failed to parse %s: %s: %s",
                f,
                type(e).__name__,
                e,
            )
            continue
        if isinstance(content, dict):
            result = deep_merge(result, content)
    return result
