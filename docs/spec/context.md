# Product Context

## Scope

### In scope

- **Confluence Server / Data Center support**: Read-only export of pages via REST API.
- **Page content types**: Processing of `page` entities and associated attachments/embedded media.
- **Input processing**: Reading and parsing plaintext URL lists containing supported URL formats (`viewpage.action?pageId=...`, `/pages/...`, `/display/...`, `/spaces/...`, bare page IDs).
- **Transformation**: Converting Confluence Storage Format XHTML to GitHub Flavored Markdown (GFM) with YAML frontmatter.
- **Macro processing**: Known macro translation (`code`, `info`, `note`, `warning`, `tip`, `expand`, `status`, `toc`, `anchor`, `table-excerpt`, `children`, `panel`) and graceful fallback.
- **Layered storage layout**: Generating 4 output layers (`01_raw`, `02_transformed`, `03_assets`, `04_markdown`), batch manifest (`manifest.json`), and run report (`run_report.json`).
- **Idempotency**: Version-based disk-skip optimization preserving existing artifacts unless `--force-refresh` is specified.
- **CLI & Environment configuration**: Standard command-line arguments and `CONFLUENCE_*` / `EXPORT_*` environment variables.

### Out of scope

- Confluence Cloud API and authentication schemes.
- Write or bidirectional synchronization operations to Confluence.
- Graphical UI, web service, daemon, or Docker/Kubernetes deployment workflows.
- Non-page content types (`blogpost`, `whiteboard`, `database`, `comment`).
- Recursive descendant page tree discovery (only URLs listed in input are exported).
- Vector store embeddings, RAG indexing, or interactive search engine integration.
- Custom raster/vector diagram rendering engines (PlantUML, Draw.io).

## Actors

- **CLI Operator / Engineer**: Runs `confluence-md-exporter` locally with credential configuration to trigger batch export.
- **Downstream Consumers**: Obsidian vault, local documentation viewers, and RAG/LLM pipelines reading generated Markdown and assets.
- **Confluence Server/Data Center Instance**: Remote upstream wiki system providing REST API access to page metadata, storage format XHTML, and attachment binaries.

## System boundaries

- **Upstream Network Boundary**: Confluence REST API (`/rest/api/content/...`). All communication is read-only over HTTPS/HTTP.
- **Local Storage Boundary**: Input file directory (`input/`) and structured output directory (`output/`).
- **Trust & Security Boundary**: Authentication credentials (PAT, Basic Auth) exist exclusively in process memory and SHALL NEVER be logged, written to disk, or embedded in output artifacts.

## Global invariants

- `INV-001` (Read-Only Safety): The system SHALL NOT issue mutating HTTP requests (`POST`, `PUT`, `DELETE`, `PATCH`) to Confluence.
- `INV-002` (Credential Protection): The system SHALL NOT log, persist, or commit secrets, tokens, or credentials to disk, logs, or output manifests.
- `INV-003` (Idempotent Execution): WHEN running without `--force-refresh`, the system SHALL skip fetching and re-transforming pages whose on-disk version matches the remote version.
- `INV-004` (Batch Error Isolation): WHEN an individual page fails due to network, auth (403), or parsing errors, the system SHALL isolate the failure, record it in `run_report.json`, and continue processing remaining items.
- `INV-005` (Lossless Macro Fallback): WHEN encountering unrecognized or malformed Confluence macros, the system SHALL preserve macro parameters and inner text in HTML comment fallbacks rather than failing the page.
- `INV-006` (Cross-Platform Filename Safety): The system SHALL generate filenames and paths compatible with both POSIX and Windows filesystem constraints, transliterating Cyrillic characters in slugs.
