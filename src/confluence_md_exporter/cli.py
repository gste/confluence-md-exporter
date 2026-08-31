"""CLI entry: load settings and refuse an impossible start with exit code 2."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections.abc import Callable, Mapping, Sequence

from confluence_md_exporter.client import ConfluenceClient
from confluence_md_exporter.settings import ConfigError, Settings, load_settings

ExportFn = Callable[[Settings], None]
AuthProbe = Callable[[Settings], None]


def parse_cli(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="confluence-md-exporter",
        description="Export Confluence Server/Data Center pages to Markdown.",
    )
    parser.add_argument("--input", default=None, help="Path to the URL list (overrides EXPORT_INPUT_FILE)")
    parser.add_argument("--output", default=None, help="Output root (overrides EXPORT_OUTPUT_DIR)")
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        default=None,
        help="Ignore disk-skip (overrides EXPORT_FORCE_REFRESH=true)",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def configure_logging(level: str) -> None:
    logging.basicConfig(level=getattr(logging, level), format="%(levelname)s %(message)s")


def _default_auth_probe(settings: Settings) -> None:
    ConfluenceClient(settings).probe()


def main(
    argv: Sequence[str] | None = None,
    environ: Mapping[str, str] | None = None,
    *,
    run_export: ExportFn | None = None,
    auth_probe: AuthProbe | None = None,
) -> int:
    try:
        args = parse_cli(argv)
        settings = load_settings(
            environ if environ is not None else os.environ,
            input_file=args.input,
            output_dir=args.output,
            force_refresh=args.force_refresh,
        )
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    configure_logging(settings.log_level)
    probe = auth_probe if auth_probe is not None else _default_auth_probe
    try:
        probe(settings)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    if run_export is not None:
        run_export(settings)
    return 0


def entry() -> None:
    raise SystemExit(main())
