"""ctl sub-subcommand package: history / maintenance / support-bundle.

CLAUDE.md §11: every ctl read-side subcommand reads on-disk artefacts
(events.jsonl, status.json, state files); ctl maintenance acquires the
state-store flock via ``StateStore.save_globals`` (CLAUDE.md §12).
"""
