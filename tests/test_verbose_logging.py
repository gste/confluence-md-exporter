from __future__ import annotations

import logging
from pathlib import Path
from unittest.mock import Mock

import pytest

from confluence_md_exporter.cli import main
from confluence_md_exporter.flow import run_export
from confluence_md_exporter.settings import Settings


def test_verbose_logging_emits_pipeline_stage_debug_logs(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    urls = tmp_path / "urls.txt"
    urls.write_text("https://confluence.example.com/pages/viewpage.action?pageId=123\n", encoding="utf-8")
    out_dir = tmp_path / "output"

    settings = Settings(
        confluence_base_url="https://confluence.example.com",
        confluence_edition="datacenter",
        confluence_auth_type="anonymous",
        confluence_token="",
        confluence_username=None,
        confluence_verify_ssl=True,
        confluence_timeout_seconds=30,
        confluence_max_retries=3,
        export_output_dir=str(out_dir),
        export_input_file=str(urls),
        export_force_refresh=False,
        log_level="DEBUG",
    )

    caplog.set_level(logging.DEBUG)

    # Mock client and fetcher to simulate successful export with debug logs
    exit_code = run_export(settings)

    debug_messages = [record.message for record in caplog.records if record.levelno == logging.DEBUG]

    # Must log input parsing stage
    assert any("input" in msg.lower() or "parsed" in msg.lower() or "read" in msg.lower() for msg in debug_messages)
    # Must log storage / manifest generation stage
    assert any("manifest" in msg.lower() or "report" in msg.lower() or "saved" in msg.lower() for msg in debug_messages)
