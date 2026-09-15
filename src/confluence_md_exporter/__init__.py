"""Local read-only Confluence Server/Data Center to Markdown exporter."""

from importlib.metadata import PackageNotFoundError, version

try:
    from confluence_md_exporter._version import __version__
except ImportError:  # pragma: no cover - source tree before hatch-vcs writes _version.py
    try:
        __version__ = version("confluence-md-exporter")
    except PackageNotFoundError:
        __version__ = "0.0.0"
