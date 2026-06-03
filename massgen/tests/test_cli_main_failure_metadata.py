"""Regression tests for execution metadata persistence on early CLI failures."""

from __future__ import annotations

import argparse
import asyncio
from pathlib import Path

import pytest
import yaml

from massgen import cli as massgen_cli
from massgen.logger_config import get_log_session_dir, reset_logging_session


@pytest.mark.usefixtures("_isolate_test_logs")
def test_execution_metadata_saved_on_missing_default_config(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Ensure fallback metadata write runs when CLI exits before normal execution."""
    monkeypatch.setenv("MASSGEN_LOG_BASE_DIR", str(tmp_path / "massgen_logs"))
    reset_logging_session()

    # Force no default config resolution so we hit the early missing-config branch.
    monkeypatch.setattr(massgen_cli.entrypoint, "resolve_config_path", lambda *_args, **_kwargs: None)

    prompt = "save prompt on early fail"
    args = argparse.Namespace(
        backend=None,
        model=None,
        config=None,
        question=prompt,
        debug=False,
        save_streaming_buffers=False,
        stream_events=False,
        logfire=False,
    )

    with pytest.raises(SystemExit):
        asyncio.run(massgen_cli.main(args))

    metadata_path = get_log_session_dir() / "execution_metadata.yaml"
    assert metadata_path.exists(), f"Expected metadata at {metadata_path}"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))

    assert metadata["query"] == prompt
    assert metadata["cli_args"]["failure_stage"] == "missing_default_config"
    assert metadata["cli_args"]["question"] == prompt
