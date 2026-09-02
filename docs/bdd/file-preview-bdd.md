# BDD Requirements: File Preview for All File Types (OTD-12)

Derived from `technical-spec.md` (Stage 1). Feature: extend the file-detail Preview panel so every
file type stored in OtterWorks renders an inline preview (or rich fallback), plus a file-service
presign `response-content-type` override so seeded objects render inline.

## Data Dependencies
- **Stores:** DynamoDB `otterworks-file-metadata` (`id`, `name`, `mime_type`, `size_bytes`, `s3_key`),
  S3 bucket `otterworks-files` (bytes at `files/<owner_id>/<file_id>`).
- **Endpoints:** `GET /api/v1/files/{id}` (metadata), `GET /api/v1/files/{id}/download` → `{url, expiresInSecs}` (presigned S3 URL).
- **Component → service → endpoint:** `file-detail.tsx` → `filesApi.get` / `filesApi.getDownloadUrl` (`src/lib/api.ts`)
  → API gateway (:8080, JWT) → file-service (Rust/Actix) → DynamoDB / S3 presign.

---

## BDD-01: Preview opens from the file list without downloading
**Traces to:** AC-01   **Category:** FUNC
**Given** a logged-in user on /files with seeded files
**When** the user clicks a file card
**Then** the detail page opens and the Preview panel renders inline content; no download is triggered
### Testing Flow
1. Log in, go to /files. 2. Click a file card. 3. Verify Preview panel shows content, no download event.

## BDD-02: Image renders inline
**Traces to:** AC-02   **Category:** FUNC
**Given** a seeded png/jpeg/svg file
**When** its detail page loads
**Then** an `<img>` renders from the presigned URL
### Testing Flow
1. Open an image file's detail page. 2. Verify the image is displayed (loaded, non-zero size).

## BDD-03: PDF renders inline despite octet-stream storage
**Traces to:** AC-03   **Category:** FUNC
**Given** a seeded PDF whose S3 object has `Content-Type: binary/octet-stream`
**When** its detail page loads
**Then** the iframe renders the PDF inline (presigned URL served with `Content-Type: application/pdf`)
### Testing Flow
1. Open a seeded PDF's detail page. 2. Verify the PDF renders in the iframe. 3. (API) curl the presigned URL and check `Content-Type: application/pdf`.

## BDD-04: Text/code renders with line numbers
**Traces to:** AC-04, AC-19   **Category:** FUNC/PERF
**Given** a seeded markdown/json/text file
**When** its detail page loads
**Then** the text preview renders with line numbers; only the first 500 KB is fetched (Range) and a truncation notice appears for larger files
### Testing Flow
1. Open a .md file's detail page. 2. Verify line-numbered content matches the real file.

## BDD-05: XLSX renders as a spreadsheet table
**Traces to:** AC-05   **Category:** FUNC
**Given** a seeded .xlsx file
**When** its detail page loads
**Then** the first sheet renders as an HTML table with sheet tabs and real cell values
### Testing Flow
1. Open a seeded xlsx detail page. 2. Verify table cells show real spreadsheet values; switch sheet tabs.

## BDD-06: CSV renders as a table
**Traces to:** AC-06   **Category:** FUNC
**Given** a seeded .csv file
**When** its detail page loads
**Then** the CSV is parsed and rendered as a table (not raw text)
### Testing Flow
1. Open a seeded csv detail page. 2. Verify a table render with header row.

## BDD-07: DOCX renders as a document
**Traces to:** AC-07   **Category:** FUNC
**Given** a seeded .docx file
**When** its detail page loads
**Then** a document-styled HTML render of the docx content appears
### Testing Flow
1. Open a seeded docx detail page. 2. Verify rendered text matches the document's real content.

## BDD-08: Audio plays inline
**Traces to:** AC-08   **Category:** FUNC
**Given** a seeded audio file (added by the updated seed generator)
**When** its detail page loads
**Then** an `<audio controls>` element renders with the presigned URL as source
### Testing Flow
1. Open a seeded audio file's detail page. 2. Verify the audio player is present and playable.

## BDD-09: Video plays inline
**Traces to:** AC-09   **Category:** FUNC
**Given** a seeded .mp4 file
**When** its detail page loads
**Then** a `<video controls>` element renders
### Testing Flow
1. Open a seeded mp4 detail page. 2. Verify the video player renders.

## BDD-10: PPTX gets the rich generic fallback
**Traces to:** AC-10   **Category:** FUNC
**Given** a seeded .pptx file
**When** its detail page loads
**Then** the fallback shows a type icon, file name, size, mime type, and a working Download button
### Testing Flow
1. Open a seeded pptx detail page. 2. Verify icon + name + size + type + Download button; click Download and verify it starts.

## BDD-11: Unknown/archive types get the generic fallback
**Traces to:** AC-11   **Category:** FUNC
**Given** a file with an unsupported mime type (e.g. application/zip)
**When** its detail page loads
**Then** the same rich fallback renders (no blank panel)
### Testing Flow
1. Upload/open a zip file. 2. Verify the rich fallback fields.

## BDD-12: Loading state while preview loads
**Traces to:** AC-12   **Category:** UI
**Given** any previewable file
**When** the presigned URL/content is in flight
**Then** a spinner is shown and the panel does not flash an error state
### Testing Flow
1. Open a file detail page. 2. Observe the spinner before content renders.

## BDD-13: Preview layout consistent across types
**Traces to:** AC-13   **Category:** UI
**Given** files of different types
**When** previews render
**Then** content stays within the panel (bounded height, internal scroll), styled like existing previews
### Testing Flow
1. Open xlsx, docx, pdf, image detail pages. 2. Verify consistent bounded layout.

## BDD-14: Preview survives back/forward navigation
**Traces to:** AC-14   **Category:** NAV
**Given** a user previews a file, navigates back to /files, then forward again
**When** using browser back/forward
**Then** the detail page re-renders the correct preview and list state is preserved
### Testing Flow
1. Open a file preview. 2. Browser back to /files. 3. Browser forward. 4. Verify preview renders again.

## BDD-15: Presign failure handled gracefully
**Traces to:** AC-15   **Category:** ERR
**Given** the download-URL request fails (missing object / API error)
**When** the detail page loads
**Then** a "No download URL available" / "Could not load preview" message renders; no crash
### Testing Flow
1. (Unit) mock a failed presign fetch. 2. Verify error message render.

## BDD-16: Oversized office/text file shows "too large" message
**Traces to:** AC-16   **Category:** ERR
**Given** an xlsx/docx over 10 MB (or text over 500 KB)
**When** its detail page loads
**Then** a "too large to preview — download instead" message with a Download button renders
### Testing Flow
1. (Unit) render spreadsheet/docx preview with size over cap. 2. Verify message + Download button.

## BDD-17: Corrupt office file falls back gracefully
**Traces to:** AC-17   **Category:** ERR
**Given** an xlsx/docx whose bytes fail to parse
**When** the preview attempts to render
**Then** the generic fallback renders instead of a crash/blank panel
### Testing Flow
1. (Unit) feed invalid bytes to the spreadsheet/docx preview. 2. Verify fallback render.

## BDD-18: Preview requires authentication
**Traces to:** AC-18   **Category:** RBAC
**Given** an unauthenticated visitor
**When** they open /files/:id
**Then** they are redirected to login (gateway returns 401 for /api/v1/files/*)
### Testing Flow
1. Logged out, navigate to a file detail URL. 2. Verify redirect to login.

## BDD-19: Download button unaffected by presign change
**Traces to:** AC-20   **Category:** FUNC
**Given** any file with the new response-content-type presign
**When** the user clicks Download
**Then** the file downloads with its original bytes
### Testing Flow
1. On a file detail page click Download. 2. Verify the download starts (toast + download event).

---

## AC → BDD Traceability Matrix

| AC-ID | Category | AC Title | BDD Scenario(s) | Status |
|-------|----------|----------|-----------------|--------|
| AC-01 | FUNC | Preview opens from file list without downloading | BDD-01 | Mapped |
| AC-02 | FUNC | Images render inline | BDD-02 | Mapped |
| AC-03 | FUNC | PDF renders inline (octet-stream objects) | BDD-03 | Mapped |
| AC-04 | FUNC | Text/code renders with line numbers | BDD-04 | Mapped |
| AC-05 | FUNC | XLSX renders as spreadsheet table | BDD-05 | Mapped |
| AC-06 | FUNC | CSV renders as table | BDD-06 | Mapped |
| AC-07 | FUNC | DOCX renders as document | BDD-07 | Mapped |
| AC-08 | FUNC | Audio plays inline | BDD-08 | Mapped |
| AC-09 | FUNC | Video plays inline | BDD-09 | Mapped |
| AC-10 | FUNC | PPTX rich fallback | BDD-10 | Mapped |
| AC-11 | FUNC | Unknown/archive generic fallback | BDD-11 | Mapped |
| AC-12 | UI | Loading state | BDD-12 | Mapped |
| AC-13 | UI | Consistent preview layout | BDD-13 | Mapped |
| AC-14 | NAV | Back/forward navigation | BDD-14 | Mapped |
| AC-15 | ERR | Presign failure handled | BDD-15 | Mapped |
| AC-16 | ERR | Oversized file message | BDD-16 | Mapped |
| AC-17 | ERR | Corrupt file fallback | BDD-17 | Mapped |
| AC-18 | RBAC | Preview requires authentication | BDD-18 | Mapped |
| AC-19 | PERF | Bounded text fetch (Range 500 KB) | BDD-04 | Mapped |
| AC-20 | FUNC | Download unaffected by presign change | BDD-19 | Mapped |

### Coverage Summary
- Total AC: 20 · Total BDD: 19 · Categories: FUNC(12) UI(2) NAV(1) ERR(3) RBAC(1) PERF(1)
- Unmapped AC-IDs: NONE
