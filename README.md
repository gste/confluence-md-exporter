# confluence-md-exporter

**English** | [Русский](README.ru.md)

Local read-only export of **Confluence Server/Data Center** pages to Markdown: page body, attachments, version diffs, and a batch report.

It does not write to Confluence, walk descendants, or talk to Cloud. Python `>=3.11,<3.15`.

## Install

```bash
pip install confluence-md-exporter
```

or

```bash
uv tool install confluence-md-exporter
```

Check: `confluence-md-exporter --version`. Help: `confluence-md-exporter -h`.

## Use cases

In every example the URL list is a UTF-8 text file, one page per line. `#…` lines and blank lines are ignored.

### Public instance

Pages are readable without login. The Confluence base URL is taken from absolute links, so `--base-url` is not needed.

`urls.txt`:

```text
https://confluence.example.com/pages/viewpage.action?pageId=123456
https://confluence.example.com/display/SPACE/Page+Title
```

```bash
confluence-md-exporter -i urls.txt -o output
```

### Private instance: Personal Access Token

Token without a username → Bearer.

```bash
confluence-md-exporter -i urls.txt -o output -t PAT
```

### Private instance: username and password (or username and PAT)

Username + token → HTTP Basic.

```bash
confluence-md-exporter -i urls.txt -o output -u USER -t TOKEN
```

### Page ids only

If the list is ids such as `123456` rather than full URLs, the base URL must be set explicitly.

`ids.txt`:

```text
123456
789012
```

```bash
confluence-md-exporter -i ids.txt -o output --base-url https://confluence.example.com
```

### Compare two versions of a page

Put a Confluence diff URL in the list. Markdown with YAML metadata and a ` ```diff ` block is written under `output/05_diffs/`.

```text
https://confluence.example.com/pages/diffpagesbyversion.action?pageId=607636678&selectedPageVersions=41&selectedPageVersions=42
```

```bash
confluence-md-exporter -i urls.txt -o output -t PAT
```

### Re-run, refresh, clean start

A second run into the same `-o` skips a page when the local version matches the server and attachment files are still on disk (disk-skip).

| Goal | Command |
|---|---|
| Fetch only what changed | `confluence-md-exporter -i urls.txt -o output` |
| Re-fetch everything, keep the directory | `confluence-md-exporter -i urls.txt -o output -r` |
| Delete the output and export from scratch | `confluence-md-exporter -i urls.txt -o output -c` |

Credentials can live in `.env` (`CONFLUENCE_TOKEN`, `CONFLUENCE_USERNAME`, …). CLI flags override the environment. Do not commit `.env`.

## Input line formats

| Kind | Example |
|---|---|
| Page by id | `https://host/pages/viewpage.action?pageId=123456` |
| Page in a space | `https://host/wiki/spaces/SPACE/pages/123456/Title` |
| Id only | `123456` (needs `--base-url` if the file has no absolute URLs) |
| Space and title | `https://host/display/SPACE/Page+Title` |
| Version diff | `…/pages/diffpagesbyversion.action?pageId=…&selectedPageVersions=41&selectedPageVersions=42` |
| Version diff | `…/diffpagesbyversion.action?pageId=…&originalVersion=41&revisedVersion=42` |

Unsupported lines (tiny-link `/x/…` and the like) are recorded in `run_report.json` as `invalid_urls` and do not fail the batch.

## Output layout

```text
output/
├── 01_raw/             # raw REST JSON
├── 02_interim/         # Storage XML
├── 03_assets/          # attachments and images (per page_id)
├── 04_markdown/        # Markdown pages and manifest.json
├── 05_diffs/           # unified diff of two versions (*_v41_to_v42.md)
└── run_report.json     # batch summary
```

## Exit codes

| Code | When |
|---|---|
| `0` | every processed page is `ok` or `skipped` |
| `1` | at least one page is `failed` |
| `2` | missing input file, bad configuration, or failed authentication |

## Development

```bash
uv sync
uv run python -m pytest
```
