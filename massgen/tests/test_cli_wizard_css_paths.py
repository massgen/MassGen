"""Regression test for wizard CSS path resolution.

The setup/quickstart/first-run wizards in ``massgen/cli/entrypoint.py`` reference
``textual_themes/dark.tcss`` relative to ``__file__``. When ``cli.py`` was split
into the ``massgen/cli/`` package, ``Path(__file__).parent`` shifted one level
deeper, breaking those paths and making ``massgen --setup`` crash with
``StylesheetError: unable to read CSS file ...``.

These tests assert that every ``CSS_PATH`` declaration in ``entrypoint.py``
points at a real ``.tcss`` file, so the same regression cannot reappear if the
module is moved again.
"""

from __future__ import annotations

import re
from pathlib import Path

import massgen.cli.entrypoint as entrypoint_module

_ENTRYPOINT_PATH = Path(entrypoint_module.__file__)
_CSS_PATH_PATTERN = re.compile(
    r"CSS_PATH\s*=\s*(Path\(__file__\)(?:\.parent)+\s*/\s*(?:\"[^\"]+\"\s*/?\s*)+)",
)
# Setup, quickstart, and first-run wizards each declare their own CSS_PATH.
# If a wizard is removed intentionally, lower this and update the comment;
# do not silently drop coverage.
_EXPECTED_WIZARD_CSS_PATH_COUNT = 3


def _resolve_css_path(expression: str) -> Path:
    """Resolve a literal ``Path(__file__).parent[...] / "a" / "b"`` expression.

    Restricted to the exact shape used in ``entrypoint.py`` so we can avoid
    ``eval`` on arbitrary code while still asserting the real filesystem result.

    Args:
        expression: The matched ``Path(__file__).parent... / "..."`` source text
            captured from ``entrypoint.py``.

    Returns:
        The filesystem path obtained by applying each ``.parent`` to
        ``entrypoint.py`` and then joining the quoted segments.
    """

    parents = expression.count(".parent")
    segments = re.findall(r"\"([^\"]+)\"", expression)
    base = _ENTRYPOINT_PATH
    for _ in range(parents):
        base = base.parent
    return base.joinpath(*segments)


def test_entrypoint_declares_expected_wizard_css_paths():
    """Pin the wizard CSS_PATH count so silent loss-of-coverage fails the test.

    The wizards in ``entrypoint.py`` (setup, quickstart, first-run) each declare
    their own ``CSS_PATH``. If one is removed by accident, the existence check
    below would still pass on whatever remained; this test forces the count to
    stay in sync with the wizard surface area.
    """

    source = _ENTRYPOINT_PATH.read_text(encoding="utf-8")
    matches = _CSS_PATH_PATTERN.findall(source)
    assert len(matches) == _EXPECTED_WIZARD_CSS_PATH_COUNT, (
        f"Expected {_EXPECTED_WIZARD_CSS_PATH_COUNT} wizard CSS_PATH declarations "
        f"in entrypoint.py (setup, quickstart, first-run); found {len(matches)}. "
        "If a wizard was intentionally removed, update _EXPECTED_WIZARD_CSS_PATH_COUNT."
    )


def test_every_wizard_css_path_resolves_to_an_existing_file():
    """Verify each wizard ``CSS_PATH`` literal resolves to a real ``.tcss`` file.

    This is the regression for the ``massgen/cli/`` package split, where every
    wizard ``CSS_PATH`` silently pointed at a nonexistent
    ``massgen/cli/frontend/...`` directory and crashed the TUI on launch.
    """

    source = _ENTRYPOINT_PATH.read_text(encoding="utf-8")
    expressions = _CSS_PATH_PATTERN.findall(source)

    missing: list[Path] = []
    for expression in expressions:
        resolved = _resolve_css_path(expression)
        if not resolved.is_file():
            missing.append(resolved)

    assert not missing, (
        "Wizard CSS_PATH declarations resolve to non-existent files. "
        "If massgen/cli/entrypoint.py was moved, update the .parent chain to "
        "point back at massgen/frontend/displays/textual_themes/.\n"
        f"Missing: {[str(p) for p in missing]}"
    )
