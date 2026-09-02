export type PreviewKind =
  | "image"
  | "video"
  | "audio"
  | "pdf"
  | "text"
  | "spreadsheet"
  | "document"
  | "generic";

export const MAX_TEXT_PREVIEW_BYTES = 500_000;
export const MAX_OFFICE_PREVIEW_BYTES = 10_000_000;
export const MAX_PREVIEW_ROWS = 200;
export const MAX_PREVIEW_COLS = 30;

const XLSX_MIME =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
const DOCX_MIME =
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

function extensionOf(fileName: string): string {
  const dot = fileName.lastIndexOf(".");
  return dot >= 0 ? fileName.slice(dot + 1).toLowerCase() : "";
}

export function previewKindFor(mimeType: string, fileName: string): PreviewKind {
  const mime = mimeType.toLowerCase();
  const extension = extensionOf(fileName);

  if (mime === "text/csv" || extension === "csv") return "spreadsheet";
  if (
    mime === XLSX_MIME ||
    mime === "application/vnd.ms-excel" ||
    extension === "xlsx" ||
    extension === "xls"
  ) {
    return "spreadsheet";
  }
  if (mime === DOCX_MIME || extension === "docx") return "document";
  if (mime.startsWith("image/")) return "image";
  if (mime.startsWith("video/")) return "video";
  if (mime.startsWith("audio/")) return "audio";
  if (mime === "application/pdf") return "pdf";
  if (
    mime.startsWith("text/") ||
    [
      "application/json",
      "application/xml",
      "application/javascript",
      "application/typescript",
      "application/x-yaml",
      "application/x-sh",
    ].includes(mime)
  ) {
    return "text";
  }
  return "generic";
}

export function isPreviewTooLarge(kind: PreviewKind, sizeBytes: number): boolean {
  return (
    (kind === "spreadsheet" || kind === "document") &&
    sizeBytes > MAX_OFFICE_PREVIEW_BYTES
  );
}

export function capGrid(rows: unknown[][]): {
  rows: string[][];
  truncatedRows: boolean;
  truncatedCols: boolean;
} {
  const truncatedRows = rows.length > MAX_PREVIEW_ROWS;
  const cappedRows = rows.slice(0, MAX_PREVIEW_ROWS);
  const truncatedCols = cappedRows.some((row) => row.length > MAX_PREVIEW_COLS);

  return {
    rows: cappedRows.map((row) =>
      row.slice(0, MAX_PREVIEW_COLS).map((cell) => String(cell ?? "")),
    ),
    truncatedRows,
    truncatedCols,
  };
}
