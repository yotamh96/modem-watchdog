"""spark-modem CLI package — argparse-based subcommand dispatch.

Phase 2 surface (FR-50): six top-level subcommands plus three ``ctl``
sub-subcommands. The entry point is wired in ``pyproject.toml``::

    [project.scripts]
    spark-modem = "spark_modem.cli.main:main"

Hardware-free laptop mode: ``diag --qmi-fixture-dir=PATH`` and
``recovery --diag-fixture=PATH`` swap a ``FixtureRunner`` into the
QmiWrapper so unit-style integration runs with no qmicli binary present.

CLAUDE.md §11: this CLI never opens an inbound IPC channel — every
read-side subcommand reads on-disk artefacts (events.jsonl, status.json,
state files); every write-side subcommand acquires the same flocks the
daemon does, via ``StateStore``.
"""
