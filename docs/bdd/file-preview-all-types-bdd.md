# BDD Requirements: File Preview for All File Types (OTD-12)

Jira: OTD-12 — "Add file preview for all file types".
Source plan: `user-story-requirement-understanding.md` + `key-design-decisions.md` (Stage 1, approved).

Preview is available from two entry points that share one component (`FilePreviewModal`):
- the **file list** ("Preview" action on a file card / list-row menu) — opens a quick-look modal without navigating away or downloading;
- the **file-detail page** (`/files/:id`) preview panel (existing surface, extended for new types).

The renderer is selected from the file's `mimeType` (DynamoDB `mime_type`, the source of truth). Blob bytes come from a **preview** presigned S3 URL: `GET /api/v1/files/{id}/download?disposition=inline`, which the file-service presigns with the real `Content-Type` and `Content-Disposition: inline` so browsers render inline even though the stored S3 object type is `binary/octet-stream`.

---

## BDD-01: Open a preview from the file list without downloading
**Traces to:** AC-01   **Category:** FUNC
**Given** I am signed in and on `/files` with files listed
**When** I open a file's row/card menu and click **Preview**
**Then** an inline preview modal opens showing the file, and no file is downloaded and the route stays on `/files`.
### Testing Flow
1. Go to `/files`, hover a file card, open the "⋮" menu.
2. Click **Preview**.
3. Verify a modal opens with the file rendered and the URL is still `/files` (no navigation, no download prompt).

## BDD-02: Image renders inline
**Traces to:** AC-02   **Category:** FUNC
**Given** a PNG or JPEG file
**When** I preview it
**Then** the image is displayed in the preview.
### Testing Flow
1. Preview a `.png`/`.jpg` (e.g. a seeded image).
2. Verify an `<img>` renders the picture (no broken-image icon).

## BDD-03: PDF renders inline
**Traces to:** AC-03   **Category:** FUNC
**Given** a PDF file
**When** I preview it
**Then** the PDF renders inline in an embedded viewer.
### Testing Flow
1. Preview a `.pdf` (seeded drive has 669).
2. Verify the embedded PDF viewer shows page content (not a download).

## BDD-04: Text / code / CSV / Markdown / JSON render as text
**Traces to:** AC-04   **Category:** FUNC
**Given** a text-family file (`text/*`, `application/json`, `application/xml`, etc.)
**When** I preview it
**Then** the file contents render as text with line numbers.
### Testing Flow
1. Preview a `.csv`/`.md`/`.json` file.
2. Verify readable text content renders in the text viewer.

## BDD-05: Spreadsheet (xlsx) renders as a table
**Traces to:** AC-05   **Category:** FUNC
**Given** an `.xlsx` file (`…spreadsheetml.sheet`)
**When** I preview it
**Then** the first sheet's cells render as an HTML table (with sheet tabs when multiple sheets exist).
### Testing Flow
1. Preview an `.xlsx` (seeded drive has 1,354).
2. Verify rows/columns render as a table with real cell values.

## BDD-06: Word document (docx) renders as formatted text
**Traces to:** AC-06   **Category:** FUNC
**Given** a `.docx` file (`…wordprocessingml.document`)
**When** I preview it
**Then** the document renders as formatted HTML (headings/paragraphs/lists).
### Testing Flow
1. Preview a `.docx` (seeded drive has 153).
2. Verify formatted document text renders.

## BDD-07: PowerPoint (pptx) graceful fallback
**Traces to:** AC-07   **Category:** FUNC
**Given** a `.pptx` file (`…presentationml.presentation`)
**When** I preview it
**Then** a graceful fallback renders (file icon + name + size + Download) with a note that inline preview isn't supported for this type — no error.
### Testing Flow
1. Preview a `.pptx` (seeded drive has 90).
2. Verify the fallback card with a Download action renders (no crash).

## BDD-08: Audio plays inline
**Traces to:** AC-08   **Category:** FUNC
**Given** an audio file (`audio/*`)
**When** I preview it
**Then** an audio player with controls is shown.
### Testing Flow
1. Preview an `audio/*` file (upload a small mp3 if none seeded).
2. Verify an `<audio controls>` element is present and playable.

## BDD-09: Video plays inline
**Traces to:** AC-09   **Category:** FUNC
**Given** a video file (`video/*`)
**When** I preview it
**Then** a video player with controls is shown.
### Testing Flow
1. Preview a `video/*` file (upload a small mp4 if none seeded).
2. Verify a `<video controls>` element is present.

## BDD-10: Graceful fallback for unsupported/unknown types
**Traces to:** AC-10   **Category:** FUNC
**Given** a file whose type has no dedicated renderer (e.g. `application/zip`) or an empty type
**When** I preview it
**Then** a fallback card shows the file icon, name, size, and a Download action — no error.
### Testing Flow
1. Upload/preview a `.zip` (or unknown type).
2. Verify the graceful fallback renders with Download.

## BDD-11: Preview URL serves the correct content-type inline
**Traces to:** AC-11   **Category:** FUNC
**Given** any binary file whose stored S3 object type is `binary/octet-stream`
**When** the preview requests `GET /api/v1/files/{id}/download?disposition=inline`
**Then** the presigned URL response carries the file's real `Content-Type` and `Content-Disposition: inline`.
### Testing Flow
1. Call the endpoint with `?disposition=inline` for a PDF; `curl -I` the returned URL.
2. Verify `Content-Type: application/pdf` and `Content-Disposition: inline` (default call without the param stays `attachment`).

## BDD-12: Preview modal chrome
**Traces to:** AC-12   **Category:** UI
**Given** a preview is open
**When** I look at the modal
**Then** it shows the filename, and a close control (X), styled per the app's design system.
### Testing Flow
1. Open any preview.
2. Verify the header shows the filename and an X close button.

## BDD-13: Loading state while the preview opens
**Traces to:** AC-13   **Category:** UI
**Given** a preview is opening and the URL/bytes are still loading
**When** I look at the modal
**Then** a loading indicator is shown until content is ready.
### Testing Flow
1. Open a preview for a larger file.
2. Verify a spinner/loading text appears before the content.

## BDD-14: Dismiss returns to the same list context
**Traces to:** AC-14   **Category:** NAV
**Given** I opened a preview from a folder/scroll position on `/files`
**When** I close it via the X, backdrop click, or the browser Back button
**Then** the modal closes and I remain on the same list view (Back closes the modal, not the app).
### Testing Flow
1. Scroll the list, open a preview, press Esc / click backdrop / press Back.
2. Verify the modal closes and the list state is unchanged.

## BDD-15: Missing / expired download URL → error state
**Traces to:** AC-15   **Category:** ERR
**Given** the preview URL is unavailable or expired
**When** I preview the file
**Then** a clear error message renders inside the modal (no crash/blank screen).
### Testing Flow
1. Simulate a failing download URL (unit test / network stub).
2. Verify an error state renders and the app stays usable.

## BDD-16: Large text file truncation
**Traces to:** AC-16   **Category:** ERR
**Given** a text file larger than 500 KB
**When** I preview it
**Then** the first 500 KB renders with a truncation notice.
### Testing Flow
1. Preview a >500 KB text file.
2. Verify the truncation notice appears.

## BDD-17: Corrupt/unreadable office file → fallback, no crash
**Traces to:** AC-17   **Category:** ERR
**Given** an `.xlsx`/`.docx` whose bytes fail to parse
**When** I preview it
**Then** a fallback message renders (no crash).
### Testing Flow
1. Feed the spreadsheet/word renderer invalid bytes (unit test).
2. Verify it renders an error/fallback state instead of throwing.

## BDD-18: RBAC — only accessible files are previewable
**Traces to:** AC-18   **Category:** RBAC
**Given** a file the current user cannot access
**When** the preview requests its metadata/download URL
**Then** the gateway/file-service denies the request (existing JWT/ownership rules); the modal shows an error.
### Testing Flow
1. Request preview for a file id not owned/shared with the user (API-level).
2. Verify a 4xx is returned and the UI shows an error.

## BDD-19: Large spreadsheet stays responsive
**Traces to:** AC-19   **Category:** PERF
**Given** a very large spreadsheet
**When** I preview it
**Then** rendered rows/cells are capped (with a "showing first N rows" note) so the UI stays responsive.
### Testing Flow
1. Preview a large `.xlsx`.
2. Verify only up to the cap renders and the modal remains responsive.

---

## AC → BDD Traceability Matrix
| AC-ID | Category | BDD(s) | Verified by |
|---|---|---|---|
| AC-01 | FUNC | BDD-01 | e2e + browser |
| AC-02 | FUNC | BDD-02 | unit (renderer) + browser |
| AC-03 | FUNC | BDD-03 | browser |
| AC-04 | FUNC | BDD-04 | unit + browser |
| AC-05 | FUNC | BDD-05 | unit (SheetJS) + browser |
| AC-06 | FUNC | BDD-06 | unit (mammoth) + browser |
| AC-07 | FUNC | BDD-07 | unit + browser |
| AC-08 | FUNC | BDD-08 | unit + browser |
| AC-09 | FUNC | BDD-09 | unit + browser |
| AC-10 | FUNC | BDD-10 | unit + browser |
| AC-11 | FUNC | BDD-11 | Rust cargo test + curl |
| AC-12 | UI | BDD-12 | unit + browser |
| AC-13 | UI | BDD-13 | unit + browser |
| AC-14 | NAV | BDD-14 | e2e + browser |
| AC-15 | ERR | BDD-15 | unit |
| AC-16 | ERR | BDD-16 | unit |
| AC-17 | ERR | BDD-17 | unit |
| AC-18 | RBAC | BDD-18 | api-flow / manual |
| AC-19 | PERF | BDD-19 | unit + browser |

**Coverage:** FUNC(11) · UI(2) · NAV(1) · ERR(3) · RBAC(1) · PERF(1) — 19/19 AC-IDs mapped, **zero unmapped**.

## Data Dependencies
- **Stores:** DynamoDB `otterworks-file-metadata` (`mime_type`, `name`, `size_bytes`, `s3_key`), S3 `otterworks-files` (blob bytes). No Postgres, no schema changes.
- **Endpoints:** `GET /api/v1/files/{id}` (metadata); `GET /api/v1/files/{id}/download[?disposition=inline]` (presigned S3 URL; inline variant sets real Content-Type + `Content-Disposition: inline`).
- **Component → service → endpoint:**
  - `FileCard`/`FilePreviewModal` → `filesApi.get` → gateway → file-service → DynamoDB.
  - `FilePreviewModal` renderers → `filesApi.getPreviewUrl` → gateway → file-service `download_file(?disposition=inline)` → S3 (LocalStack).
