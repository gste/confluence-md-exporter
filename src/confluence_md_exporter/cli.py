"""CLI entry: load settings and refuse an impossible start with exit code 2."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from confluence_md_exporter.client import ConfluenceClient
from confluence_md_exporter.flow import run_export as default_run_export
from confluence_md_exporter.settings import ConfigError, Settings, load_settings

ExportFn = Callable[[Settings], int | None]
AuthProbe = Callable[[Settings], None]


def parse_cli(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="confluence-md-exporter",
        description="Export Confluence Server/Data Center pages to Markdown.",
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input",
        default=None,
        help="Path to the URL list (overrides EXPORT_INPUT_FILE)",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        default=None,
        help="Output root (overrides EXPORT_OUTPUT_DIR)",
    )
    parser.add_argument(
        "-r",
        "--refresh",
        "--force-refresh",
        dest="force_refresh",
        action="store_true",
        default=None,
        help="Ignore disk-skip and refresh cached content (overrides EXPORT_FORCE_REFRESH=true)",
    )
    parser.add_argument(
        "-c",
        "--clean",
        dest="clean",
        action="store_true",
        default=False,
        help="Clean output directory before export",
    )
    parser.add_argument(
        "-s",
        "--simple",
        dest="simple",
        action="store_true",
        default=False,
        help="Ignored: export is always single-threaded",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s %(levelname)-7s %(message)s",
        datefmt="%H:%M:%S",
    )


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

    if args.clean:
        output_dir = Path(settings.export_output_dir)
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

    export_fn = run_export if run_export is not None else default_run_export
    result = export_fn(settings)
    return result if isinstance(result, int) else 0


def entry() -> None:
    raise SystemExit(main())
