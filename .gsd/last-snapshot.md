# GSD context snapshot (2026-05-19T12:56:31.441Z)

## Top project memories
- [MEM007] (gotcha) Postinst smoke gates that only import runtime libs (not the daemon/CLI packages themselves) give false confidence — broken imports in application code pass the gate. Always smoke-import the actual entry-point modules (e.g. spark_modem.daemon.main, spark_modem.cli.main).
- [MEM010] (convention) pytest-asyncio mode=auto eliminates need for per-test @pytest.mark.asyncio decorators and module-level pytestmark assignments. Redundant markers are a lint violation. Do not add them — the framework handles async test detection automatically.
- [MEM011] (gotcha) Target platform L4T R35.6.4 ships systemd 245, not 247+. Features like LoadCredential= silently do nothing on 245. CI must run systemd-analyze verify against the target systemd version, and code must include fallback paths for missing 247+ features.
- [MEM003] (pattern) Belt-and-suspenders smoke test: place smoke-import gates in TWO locations — postinst (catches broken .deb install) and systemd ExecStartPre (catches runtime path issues). Neither alone is sufficient; both are cheap and catch different failure classes.
- [MEM006] (pattern) Unit-file audit tests cross-check pyproject.toml [project.scripts] against debian/.install against systemd ExecStart* paths. Catches the class of bug where one path is updated but the others drift out of sync.
- [MEM008] (gotcha) Python Protocol structural matching under mypy --strict requires exact type variance. Using `kind: object` in a Protocol won't match `kind: ActionKind` in the implementation. Must import and use the exact concrete type in Protocol definitions.
