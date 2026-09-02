# Technical Spec: File Preview for All File Types (OTD-12)

## 1. Context & Goal
**Story:** OTD-12 — "Add file preview for all file types"
> As a user, I want to preview files of any type directly in OtterWorks without downloading them, so I can quickly view file contents inline.
>
> Acceptance Criteria (verbatim): Users can open a preview for a file from the file list without downloading it. Preview correctly renders common types (images, PDF, text/code) and gracefully falls back for unsupported types. Preview works across all file types stored in OtterWorks.

**Goal:** Extend the existing file-detail Preview panel so every file type stored in OtterWorks renders an appropriate inline preview (or a rich, graceful fallback), and fix the presigned-URL Content-Type so previews of seeded files actually render inline.
**Location:** `frontend/client-app` (React/Vite) — `src/pages/file-detail.tsx`, `src/components/files/file-preview.tsx`; plus a small change in `services/file-service` (Rust/Actix) `download_file`.
**Trigger:** User clicks a file in the file list (`FileCard` → `/files/:id`); the detail page's Preview panel renders based on `file.mimeType`.

**Interview resolutions (Step 3):**
1. Extend the existing detail-page preview only (no list modal/lightbox).
2. Office docs render client-side: SheetJS for xlsx + csv, docx-preview (or mammoth) for docx; pptx gets a rich fallback (icon + metadata + Download) — no server-side conversion.
3. Approved: file-service presigns with `response-content-type` from stored metadata.
4. Approved: add an `<audio>` player branch AND seed a few sample audio files for demo/verification.
5. Generic fallback = icon + name/size/type + Download button; size cap for client-rendered office/text previews with "too large to preview — download instead" message.
6. Out of scope confirmed (see §6).

## 2. Requirement Understanding

### Technical Constraints
**Stack:** React 18 + Vite client-app (`@tanstack/react-query`, axios `apiClient`, Tailwind, lucide-react); Go/Chi API gateway (:8080, JWT-gated `/api/v1/files/*`); Rust/Actix file-service (:8082); metadata in DynamoDB, bytes in S3 (LocalStack locally).
**Conventions:** same-origin `/api/v1` proxy via `src/lib/api-client.ts`; `filesApi` in `src/lib/api.ts`; presigned URL host rewritten `localstack:`→`localhost:` in `filesApi.getDownloadUrl`; preview components colocated in `src/components/files/file-preview.tsx`; loading/empty/error states follow existing spinner/AlertCircle patterns.
**New dependencies (frontend only):** `xlsx` (SheetJS) and `docx-preview` — both mature, published well over 7 days ago; no backend deps added.

### Database / Data Dependencies (verified against the live local store)

#### Tables / Stores Involved
| Table / Store | Purpose | Key Columns / Keys | Notes |
|---|---|---|---|
| DynamoDB `otterworks-file-metadata` | File metadata (source of `mimeType`, `name`, `size`) | `id` (S, UUID), `name`, `mime_type`, `size_bytes`, `s3_key`, `owner_id`, `folder_id`, `updated_at`, `created_at`, `is_trashed`, `version` | 2,175 seeded items; read-only for this feature |
| S3 bucket `otterworks-files` | File bytes | key `files/<owner_id>/<file_id>` | Range requests honored (`accept-ranges: bytes`); seeded objects stored with `Content-Type: binary/octet-stream` |

No Postgres changes. No DynamoDB schema changes.

#### Column/Contract Mapping (all ✅)
| Output/Input Field | Source Store | Source Column / Attribute / API field | Verified? | Sample Value | Notes |
|---|---|---|---|---|---|
| `file.id` | DynamoDB `otterworks-file-metadata` | `id` | ✅ | `715d56db-…` | via `GET /api/v1/files/{id}` |
| `file.name` | DynamoDB | `name` | ✅ | `DC Southeast Throughput Q2 2024.xlsx` | shown in preview header/fallback |
| `file.mimeType` | DynamoDB | `mime_type` | ✅ | `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | drives preview-type dispatch |
| `file.size` | DynamoDB | `size_bytes` | ✅ | `15663` | size-cap check + fallback display |
| presigned URL | `GET /api/v1/files/{id}/download` (file-service `download_file` → S3 presign) | response `{url, expiresInSecs}` | ✅ | tested live, HTTP 200 | will add `response-content-type` override |
| file bytes | S3 `otterworks-files` | object at `s3_key` | ✅ | real OOXML/PDF content | fetched by browser directly via presigned URL |

#### Data Values & Enums (live `mime_type` distribution, 2,175 files)
| Observed `mime_type` | Count | Preview treatment |
|---|---|---|
| `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet` | 1,066 | NEW: SheetJS table render |
| `application/pdf` | 640 | existing iframe (fixed by content-type override) |
| `text/csv` | 124 | NEW: SheetJS table render (falls under text today) |
| `application/vnd.openxmlformats-officedocument.wordprocessingml.document` | 117 | NEW: docx-preview render |
| `image/png`, `image/jpeg`, `image/svg+xml` | 122 | existing `<img>` |
| `application/vnd.openxmlformats-officedocument.presentationml.presentation` | 90 | NEW: rich fallback (icon + metadata + Download) |
| `text/markdown`, `application/json` | 13 | existing text/code preview |
| `video/mp4` | 3 | existing `<video>` |
| `audio/*` | 0 today | NEW: `<audio>` branch + seed sample audio files |

#### Join / Call Path
```
FileCard (files.tsx list) → Link /files/:id
  → FileDetailPage: useQuery filesApi.get(id)          → GET /api/v1/files/{id}        (gateway → file-service → DynamoDB)
  → useQuery filesApi.getDownloadUrl(id)               → GET /api/v1/files/{id}/download (gateway → file-service → S3 presign)
  → FilePreviewContent dispatches on file.mimeType     → browser fetches presigned S3 URL directly (Range where applicable)
```

### Data Shape & Interfaces
**Inputs:** `GET /api/v1/files/{id}` (FileItem incl. `mimeType`, `size`); `GET /api/v1/files/{id}/download` → `{ url, expiresInSecs }`.
**Outputs:** rendered preview only — no new API routes, no writes, no state changes. The only contract change: `download_file` presigns with `response-content-type=<stored mime_type>` (same JSON response shape).

## 3. Acceptance Criteria Matrix

| # | AC-ID | Category | Scenario | Given | When | Then | Priority | Design impact | Verification |
|---|---|---|---|---|---|---|---|---|---|
| 1 | AC-01 | FUNC | Preview opens from file list without downloading | Logged-in user on /files with seeded files | User clicks a file card | Detail page opens and the Preview panel renders inline content; no file download is triggered | Must | `FileCard` → `file-detail.tsx` (existing nav), `GET /api/v1/files/{id}/download` | Playwright: click card, assert preview content visible, no download event |
| 2 | AC-02 | FUNC | Images render inline | A seeded png/jpeg/svg file | Detail page loads | `<img>` renders from presigned URL | Must | `ImageFilePreview`, presign override | Playwright: img element loaded (naturalWidth>0) |
| 3 | AC-03 | FUNC | PDF renders inline (seeded octet-stream objects) | A seeded PDF (S3 Content-Type `binary/octet-stream`) | Detail page loads | iframe renders the PDF inline instead of downloading | Must | `PdfFilePreview`; file-service `download_file` `response_content_type` | Playwright: iframe present; curl presigned URL returns `Content-Type: application/pdf` |
| 4 | AC-04 | FUNC | Text/code renders with line numbers | A seeded md/json/text file | Detail page loads | Text preview table renders content; >500 KB shows truncation notice | Must | `TextFilePreview` (existing) | Vitest component test + Playwright spot check |
| 5 | AC-05 | FUNC | XLSX renders as a spreadsheet table | A seeded xlsx file | Detail page loads | First sheet renders as an HTML table with sheet tabs; real cell values visible | Must | NEW `SpreadsheetFilePreview` (SheetJS), `file-preview.tsx` | Playwright: table cells contain expected seeded values |
| 6 | AC-06 | FUNC | CSV renders as a table | A seeded csv file | Detail page loads | CSV parsed and rendered as a table (not raw text) | Must | `SpreadsheetFilePreview` handles text/csv | Playwright: table render for csv file |
| 7 | AC-07 | FUNC | DOCX renders as a document | A seeded docx file | Detail page loads | Paginated/document-style HTML render of the docx content | Must | NEW `DocxFilePreview` (docx-preview lib) | Playwright: rendered text matches seeded doc content |
| 8 | AC-08 | FUNC | Audio plays inline | A seeded audio file (to be seeded) | Detail page loads | `<audio controls>` renders and can play | Must | NEW audio branch in `FilePreviewContent`; seed script addition | Playwright: audio element with src present |
| 9 | AC-09 | FUNC | Video plays inline | A seeded mp4 | Detail page loads | `<video controls>` renders (existing) | Must | existing video branch + content-type override | Playwright: video element present |
| 10 | AC-10 | FUNC | PPTX gets rich fallback | A seeded pptx file | Detail page loads | Fallback shows icon + name + size + type + working Download button (no blank panel) | Must | NEW `GenericFilePreview` | Playwright: fallback fields + download click works |
| 11 | AC-11 | FUNC | Unknown/archive types get generic fallback | A file with unsupported mime (e.g. zip) | Detail page loads | Same rich fallback as AC-10 | Must | `GenericFilePreview` | Vitest component test with zip mime |
| 12 | AC-12 | UI | Loading state while presign/content loads | Any previewable file | Preview data is in flight | Spinner shown; layout does not jump to error state | Must | `FilePreviewContent` loading branch | Vitest: loading render |
| 13 | AC-13 | UI | Preview panel layout consistent across types | Files of each type | Switching between files | Preview stays within panel (max heights, scroll inside), consistent with existing styles | Should | `file-preview.tsx` styles | Playwright screenshots per type |
| 14 | AC-14 | NAV | Preview survives navigation back/forward | User previews file A, goes back to /files, forward again | Browser back/forward | Detail page re-renders correct preview; list state (folder, view mode) preserved | Must | react-query cache keys `["files", id]` | Playwright: back/forward assertions |
| 15 | AC-15 | ERR | Presign failure handled | download URL request fails (e.g. file missing in S3) | Detail page loads | "No download URL available" / "Could not load preview" message, no crash | Must | error branches in preview components | Vitest: mock URL failure |
| 16 | AC-16 | ERR | Oversized office/text file | xlsx/docx/text over size cap (10 MB office / 500 KB text) | Detail page loads | "Too large to preview — download instead" message + Download button | Must | size-cap check using `file.size` | Vitest: oversized file mock |
| 17 | AC-17 | ERR | Corrupt/unparseable office file | xlsx/docx bytes fail to parse | Parse throws | Graceful fallback to generic preview (no white screen) | Must | try/catch → `GenericFilePreview` | Vitest: corrupt bytes mock |
| 18 | AC-18 | RBAC | Preview requires authentication | Unauthenticated visitor | Opens /files/:id | Redirected to login; `/api/v1/files/*` returns 401 via gateway JWT middleware | Must | existing gateway JWT middleware (no change) | Playwright: logged-out redirect |
| 19 | AC-19 | PERF | Preview fetch is bounded | Large text file | Text preview loads | Range request fetches only first 500 KB (existing behavior preserved) | Should | `TextFilePreview` Range header | Vitest/network assertion |
| 20 | AC-20 | FUNC | Download button unaffected by presign change | Any file | User clicks Download | File downloads with original bytes (content-type override does not force inline-only or break download) | Must | `download_file` handler change | Playwright: download event fires; service test on presign params |

### Completeness Checklist
- [x] ≥1 FUNC per data field/endpoint (AC-01…AC-11, AC-20)
- [x] ≥1 UI (AC-12, AC-13)
- [x] ≥1 NAV (AC-14)
- [x] ≥1 ERR per error path (AC-15 presign, AC-16 size, AC-17 parse)
- [x] RBAC (AC-18)
- [x] PERF (AC-19)
- [x] every AC has a unique AC-ID

## 4. Key Design Decisions

### Decisions
| Decision | Rationale | Alternatives |
|---|---|---|
| Extend detail-page preview only; no list modal | User's choice (interview #1); FileCard already navigates to `/files/:id` which satisfies "open from the file list" | Drive-style lightbox modal (rejected: scope) |
| Client-side office rendering (SheetJS xlsx/csv, docx-preview docx) | Frontend-only, no new service/container; 59% of seeded corpus becomes previewable | LibreOffice server-side conversion (rejected: heavy new dependency, bigger scope) |
| PPTX → rich generic fallback | No credible client-side pptx renderer; graceful fallback is an explicit story AC | Server conversion (rejected) |
| file-service presigns with `response-content-type` from stored `mime_type` | Seeded S3 objects are `binary/octet-stream`; without override, PDF/image/video previews won't render inline. Approved in interview #3 | Re-upload 2,175 objects with correct types (rejected: mutates shared seed data); frontend blob-fetch workaround (rejected: doubles downloads) |
| Add `<audio>` branch + seed sample audio files | Approved in interview #4; closes the "all file types" gap and makes it demoable | Skip audio (rejected by user) |
| Shared `GenericFilePreview` fallback (icon + name/size/type + Download) | User's choice (interview #5); reused for pptx, archives, unknown, oversized, corrupt | Plain text message (current behavior, rejected) |

### AC → Design Traceability
| AC-ID | Layer | Change (file/route/query) | Decision ref |
|---|---|---|---|
| AC-01, AC-14, AC-18 | FE (existing) | `file-detail.tsx` routing/query wiring (unchanged) | Extend detail page |
| AC-02, AC-04, AC-09, AC-12, AC-13, AC-19 | FE | `file-preview.tsx` existing components (minor style/state alignment) | Extend detail page |
| AC-03, AC-20 | Service | `services/file-service/src/handlers.rs` `download_file` + `storage.rs` `presigned_download_url(key, expires, content_type)` | response-content-type override |
| AC-05, AC-06, AC-16, AC-17 | FE | NEW `SpreadsheetFilePreview` in `file-preview.tsx` (dep: `xlsx`) | Client-side office rendering |
| AC-07, AC-16, AC-17 | FE | NEW `DocxFilePreview` (dep: `docx-preview`) | Client-side office rendering |
| AC-08 | FE + seed | audio branch in `FilePreviewContent`; add audio files in `testdata/generated/retail-drive/generate_drive.py` | Audio support |
| AC-10, AC-11, AC-15 | FE | NEW `GenericFilePreview` replacing bare fallback | Rich fallback |

## 5. Architecture & Layer Breakdown

**Data flow (unchanged shape):**
```
file-detail.tsx ── GET /api/v1/files/{id} ──────────► gateway ──► file-service ──► DynamoDB otterworks-file-metadata
              └─── GET /api/v1/files/{id}/download ─► gateway ──► file-service ──► S3 presign (now with response-content-type)
FilePreviewContent(mimeType) ── browser fetch(presignedUrl) ──► LocalStack/S3 (Range honored)
```

**Layer changes:**
- **Data:** none (read-only). Seed generator gains a handful of small audio files (`audio/mpeg` or `audio/wav`) uploaded through the real gateway like all other seed data.
- **Backend (file-service, Rust/Actix):**
  - `storage.rs`: `presigned_download_url` accepts an optional content type and sets `.response_content_type(...)` on the `get_object` presign builder.
  - `handlers.rs` `download_file`: pass `file.mime_type` from DynamoDB metadata. Response DTO unchanged. Also applies to version download URLs if they use the same presign helper.
- **Frontend (`frontend/client-app`):**
  - `file-detail.tsx`: extend the mime dispatch — add `isAudio`, `isSpreadsheet` (xlsx + text/csv), `isDocx`, and route pptx/unknown to `GenericFilePreview`; pass `file.size` down for size-cap checks.
  - `file-preview.tsx`: add `SpreadsheetFilePreview` (fetch presigned URL as ArrayBuffer → SheetJS → HTML table with sheet tabs, capped rows/cols with "showing first N rows" note), `DocxFilePreview` (fetch ArrayBuffer → docx-preview render into a container), `AudioFilePreview` (`<audio controls src>`), `GenericFilePreview` (icon by mime, name, size, type, Download button reusing `filesApi.getDownloadUrl` flow). All with loading spinner / error / oversized states matching existing patterns.
  - `package.json`: add `xlsx`, `docx-preview`.

## 6. Edge Cases, Security & Constraints

### Error Handling & Edge Cases
- Presign request fails → existing "No download URL available" state (AC-15).
- Office/text file over cap (10 MB office, 500 KB text) → "too large to preview" + Download (AC-16).
- Parse failure on xlsx/docx → catch and render `GenericFilePreview` (AC-17).
- Empty file (0 bytes) → office/text previews render an "empty file" note instead of a parser error.
- SVG images render via `<img>` (sanitized by browser context; no inline `dangerouslySetInnerHTML`).
- Presigned URL expiry (1 h, staleTime 30 min already set) — unchanged.

### RBAC & Security
- No role changes: any authenticated user who can fetch the file metadata can preview it (same as Download today). Gateway JWT middleware already protects `/api/v1/files/*`.
- No secrets, no new endpoints, no data writes.

### Integration Points
- LocalStack S3 (local) / real S3 (deployed): `response_content_type` presign param is standard S3, works on both (verified LocalStack honors response-* overrides).
- Seed generator `testdata/generated/retail-drive/generate_drive.py` — additive audio entries only.

### Impact on Shared/Existing Objects
| Object | Change | Dependents | Approval |
|---|---|---|---|
| `file-service` `download_file` / `presigned_download_url` | add response-content-type override | Download button (files list + detail), version downloads, seed loader | ✅ approved (interview #3) |
| `file-preview.tsx` | new components added; existing three unchanged in behavior | `file-detail.tsx` only (verified via grep) | ✅ (additive) |
| `file-detail.tsx` dispatch | extended branches | none (page-level) | ✅ (additive) |
| retail-drive seed generator | additive audio samples | snapshot seeding blueprint | ✅ approved (interview #4) |

### Negative Constraints (Out of Scope — confirmed in interview #6)
- DO NOT implement in this planning stage.
- NO list-grid thumbnails; NO quick-preview modal from the list; NO preview on Search/Shared/Trash pages; NO admin-dashboard, mobile, or Electron work; NO server-side conversion service.
- DO NOT fix planted bugs (e.g. admin-service `production.rb` logger crash).
- DO NOT use mock/hardcoded data or bypass the API/DB — all previews fetch real bytes via the real presigned-URL flow.
- DO NOT modify shared objects beyond the two approved changes above.

## 7. Pre-Implementation Checklist
- [x] All Column/Contract Mapping fields ✅ (verified against live DynamoDB/S3/gateway)
- [x] Every AC has Design impact + Verification filled in
- [x] Every AC appears in the AC → Design traceability table
- [x] All shared-object changes explicitly approved (interview #3, #4)
- [ ] User has given explicit go-ahead to implement (Stage 2: `!user_story_to_bdd_verified_pr`)
