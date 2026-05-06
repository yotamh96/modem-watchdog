"""Tests for spark_modem.cli.main — argparse subcommand dispatch."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from spark_modem.cli import diag as diag_cmd
from spark_modem.cli import main as cli_main


def test_main_help_prints_usage(capsys: pytest.CaptureFixture[str]) -> None:
    """`--help` exits 0 and prints usage text."""
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["--help"])
    captured = capsys.readouterr()
    assert exc_info.value.code == 0
    assert "usage:" in captured.out.lower() or "usage:" in captured.err.lower()


def test_main_unknown_command_exits_2(capsys: pytest.CaptureFixture[str]) -> None:
    """Unknown subcommand → SystemExit(2)."""
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main(["unknown"])
    assert exc_info.value.code == 2


def test_main_missing_subcommand_exits_2() -> None:
    """No subcommand → SystemExit(2)."""
    with pytest.raises(SystemExit) as exc_info:
        cli_main.main([])
    assert exc_info.value.code == 2


def test_main_diag_dispatches_to_diag_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`spark-modem diag --qmi-fixture-dir=... --json` dispatches to diag_cmd.run."""
    captured: dict[str, Any] = {}

    async def fake_run(args: Any) -> int:
        captured["called"] = True
        captured["qmi_fixture_dir"] = args.qmi_fixture_dir
        captured["json"] = args.json
        return 0

    monkeypatch.setattr(diag_cmd, "run", fake_run)
    rc = cli_main.main(["diag", "--qmi-fixture-dir=tests/fixtures/qmicli", "--json"])
    assert rc == 0
    assert captured["called"] is True
    assert captured["qmi_fixture_dir"] == "tests/fixtures/qmicli"
    assert captured["json"] is True


def test_main_returns_handler_exit_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """main() returns whatever the handler returns."""

    async def fake_run(args: Any) -> int:
        del args
        return 7

    monkeypatch.setattr(diag_cmd, "run", fake_run)
    rc = cli_main.main(["diag", "--qmi-fixture-dir=anything", "--json"])
    assert rc == 7


def test_main_module_has_callable_entry() -> None:
    """The pyproject.toml entry point references this exact callable."""
    assert callable(cli_main.main)


def test_main_pyproject_scripts_contains_spark_modem() -> None:
    """pyproject.toml registers `spark-modem = "spark_modem.cli.main:main"`."""
    pyproject = Path(__file__).parents[3] / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert "[project.scripts]" in text
    assert 'spark-modem = "spark_modem.cli.main:main"' in text
