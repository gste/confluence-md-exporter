"""Local read-only Confluence Server/Data Center to Markdown exporter."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("confluence-md-exporter")
except PackageNotFoundError:  # pragma: no cover - source tree without install
    __version__ = "1.0.0"
