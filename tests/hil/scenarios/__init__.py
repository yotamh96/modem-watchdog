"""HIL scenario suite (Plan 04-07).

12 scenario files mapping to Phase 4 SC#4 (FR-24) plus the four Phase 3
deferred SC piggybacks (CONTEXT D-04). Each file sets its own
``pytestmark = [linux_only, hil, skipif(win32), asyncio]``; the parent
package's ``__init__.py`` is intentionally empty so collection on
non-Linux dev hosts is gated by the conftest's ``collect_ignore_glob``
in ``tests/hil/conftest.py``.
"""
