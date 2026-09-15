"""CLI entry: load settings and refuse an impossible start with exit code 2."""

from __future__ import annotations

import argparse
import logging
import os
import shutil
import sys
from collections.abc import Callable, Mapping, Sequence
from pathlib import Path

from confluence_md_exporter import __version__
from confluence_md_exporter.client import ConfluenceClient
from confluence_md_exporter.flow import run_export as default_run_export
from confluence_md_exporter.settings import ConfigError, Settings, load_settings

ExportFn = Callable[[Settings], int | None]
AuthProbe = Callable[[Settings], None]

_HELP_EPILOG = """\
Defaults: input/urls.txt, output/, anonymous access.
The Confluence base URL is inferred from absolute URLs in the list.

Examples:
  confluence-md-exporter -i urls.txt -o output
      public instance, full page URLs in the list

  confluence-md-exporter -i urls.txt -o output -t PAT
      private instance, Personal Access Token (Bearer)

  confluence-md-exporter -i urls.txt -o output -u USER -t TOKEN
      private instance, HTTP Basic (username + PAT/password)

  confluence-md-exporter -i ids.txt -o output -b https://confluence.example.com
      page ids only, base URL set explicitly

  confluence-md-exporter -i urls.txt -o output -c
      wipe the output directory and export from scratch

  confluence-md-exporter -i urls.txt -o output -r
      do not skip pages whose version is already on disk

Exit codes: 0 ok/skipped; 1 some pages failed; 2 config, auth, or missing input file.
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="confluence-md-exporter",
        description=(
            "Local read-only export of Confluence Server/Data Center pages "
            "to Markdown, attachments, and version diffs."
        ),
        epilog=_HELP_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    parser.add_argument(
        "-i",
        "--input",
        dest="input",
        metavar="FILE",
        default=None,
        help="URL list (default: input/urls.txt)",
    )
    parser.add_argument(
        "-o",
        "--output",
        dest="output",
        metavar="DIR",
        default=None,
        help="output directory (default: output)",
    )
    parser.add_argument(
        "-r",
        "--refresh",
        "--force-refresh",
        dest="force_refresh",
        action="store_true",
        default=None,
        help="ignore disk-skip and re-fetch pages",
    )
    parser.add_argument(
        "-c",
        "--clean",
        dest="clean",
        action="store_true",
        default=False,
        help="wipe the output directory before export",
    )
    parser.add_argument(
        "-u",
        "--user",
        "--username",
        dest="username",
        metavar="USER",
        default=None,
        help="username; with -t uses HTTP Basic",
    )
    parser.add_argument(
        "-t",
        "--token",
        "--api-token",
        dest="token",
        metavar="TOKEN",
        default=None,
        help="Personal Access Token or password; -t alone uses Bearer",
    )
    parser.add_argument(
        "-b",
        "--base-url",
        dest="base_url",
        metavar="URL",
        default=None,
        help="instance base URL if it cannot be inferred from the list",
    )
    parser.add_argument(
        "-s",
        "--simple",
        dest="simple",
        action="store_true",
        default=False,
        help=argparse.SUPPRESS,
    )
    return parser


def parse_cli(argv: Sequence[str] | None = None) -> argparse.Namespace:
    return build_parser().parse_args(list(argv) if argv is not None else None)


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
            base_url=args.base_url,
            username=args.username,
            token=args.token,
        )
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    configure_logging(settings.log_level)
    if settings.confluence_auth_type == "anonymous":
        logging.getLogger(__name__).info("Access: anonymous")
    else:
        logging.getLogger(__name__).info(
            "Access: %s%s",
            settings.confluence_auth_type,
            f" user={settings.confluence_username}" if settings.confluence_username else "",
        )
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
