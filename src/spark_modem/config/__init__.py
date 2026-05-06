"""config — Settings + YAML merger + reload-marker convention."""

from spark_modem.config.reload_marker import (
    RELOAD_DATA,
    RELOAD_RESTART,
    data_reloadable_fields,
    reload_class,
    restart_required_fields,
)
from spark_modem.config.settings import Settings
from spark_modem.config.yaml_merge import deep_merge, load_yaml_layer

__all__ = [
    "RELOAD_DATA",
    "RELOAD_RESTART",
    "Settings",
    "data_reloadable_fields",
    "deep_merge",
    "load_yaml_layer",
    "reload_class",
    "restart_required_fields",
]
