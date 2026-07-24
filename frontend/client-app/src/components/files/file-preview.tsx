import { useState, useEffect } from "react";
import { File, AlertCircle, Download, FileWarning } from "lucide-react";
import { formatFileSize } from "@/lib/utils";
import type { WorkBook as XLSXWorkBook } from "xlsx";

// xlsx and mammoth are heavy; load them on demand so they are code-split out of
// the initial bundle and only fetched when an office file is previewed.
const loadXLSX = () => import("xlsx");
const loadMammoth = () => import("mammoth");

const MAX_PREVIEW_SIZE = 500_000; // 500 KB — truncate beyond this
const MAX_SHEET_ROWS = 500; // cap rendered spreadsheet rows to stay responsive

interface TextFilePreviewProps {
  presignedUrl?: string;
  fileName: string;
}

export function TextFilePreview({ presignedUrl, fileName }: TextFilePreviewProps) {
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [truncated, setTruncated] = useState(false);
  // Falls back to iframe when fetch() is blocked (e.g. CORS on cross-origin S3 URLs)
  const [useIframeFallback, setUseIframeFallback] = useState(false);

  useEffect(() => {
    if (!presignedUrl) {
      setLoading(false);
      return;
    }

    let cancelled = false;
    setLoading(true);
    setContent(null);
    setUseIframeFallback(false);

    fetch(presignedUrl, {
      headers: { Range: `bytes=0-${MAX_PREVIEW_SIZE - 1}` },
    })
      .then(async (res) => {
        // 206 = partial content (Range honored), 200 = full file (Range ignored)
        if (!res.ok && res.status !== 206) throw new Error(`HTTP ${res.status}`);
        const text = await res.text();
        if (cancelled) return;
        setContent(text);
        setTruncated(res.status === 206);
      })
      .catch(() => {
        if (!cancelled) setUseIframeFallback(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [presignedUrl]);

  if (loading) {
    return (
      <div className="w-full text-center py-8">
        <div className="w-6 h-6 border-2 border-otter-600 border-t-transparent rounded-full animate-spin mx-auto" />
        <p className="text-xs text-gray-400 mt-2">Loading preview…</p>
      </div>
    );
  }

  if (!presignedUrl) {
    return (
      <div className="text-center py-8">
        <AlertCircle size={48} className="text-gray-300 mx-auto mb-3" />
        <p className="text-sm text-gray-500">No download URL available</p>
      </div>
    );
  }

  if (useIframeFallback) {
    return (
      <div className="w-full">
        <iframe
          src={presignedUrl}
          className="w-full min-h-[500px] bg-white rounded-lg border border-gray-200"
          sandbox="allow-same-origin"
          title={`Preview of ${fileName}`}
        />
      </div>
    );
  }

  if (content === null) {
    return (
      <div className="text-center py-8">
        <AlertCircle size={48} className="text-gray-300 mx-auto mb-3" />
        <p className="text-sm text-gray-500">Could not load preview</p>
      </div>
    );
  }

  const lines = content.split("\n");
  const gutterWidth = String(lines.length).length;

  return (
    <div className="w-full">
      <div className="rounded-lg border border-gray-200 bg-white overflow-hidden">
        <div className="flex items-center justify-between px-4 py-2 bg-gray-50 border-b border-gray-200">
          <span className="text-xs font-medium text-gray-500 truncate">
            {fileName}
          </span>
          <span className="text-xs text-gray-400">
            {lines.length} line{lines.length !== 1 ? "s" : ""}
          </span>
        </div>
        <div className="overflow-auto max-h-[600px]">
          <table className="w-full border-collapse">
            <tbody>
              {lines.map((line, i) => (
                <tr key={i} className="hover:bg-gray-50">
                  <td
                    className="sticky left-0 bg-gray-50 text-right select-none px-3 py-0 text-xs text-gray-400 font-mono border-r border-gray-200"
                    style={{ minWidth: `${gutterWidth + 2}ch` }}
                  >
                    {i + 1}
                  </td>
                  <td className="px-4 py-0 whitespace-pre font-mono text-sm text-gray-800 overflow-x-auto">
                    {line || "\u00A0"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
      {truncated && (
        <p className="text-xs text-amber-600 mt-2 text-center">
          File truncated — showing first {(MAX_PREVIEW_SIZE / 1000).toFixed(0)} KB. Download the file to see full contents.
        </p>
      )}
    </div>
  );
}

interface PdfFilePreviewProps {
  presignedUrl?: string;
}

export function PdfFilePreview({ presignedUrl }: PdfFilePreviewProps) {
  if (!presignedUrl) {
    return (
      <div className="text-center py-8">
        <File size={64} className="text-red-400 mx-auto mb-3" />
        <p className="text-sm text-gray-500">PDF preview not available</p>
      </div>
    );
  }

  return (
    <div className="w-full">
      <iframe
        src={presignedUrl}
        className="w-full rounded-lg border border-gray-200"
        style={{ minHeight: "600px" }}
        title="PDF preview"
      />
      <p className="text-xs text-gray-400 mt-2 text-center">
        If the preview doesn&apos;t load,{" "}
        <a
          href={presignedUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-otter-600 hover:underline"
        >
          open in a new tab
        </a>
      </p>
    </div>
  );
}

interface ImageFilePreviewProps {
  presignedUrl?: string;
  fileName: string;
}

export function ImageFilePreview({ presignedUrl, fileName }: ImageFilePreviewProps) {
  const [error, setError] = useState(false);

  useEffect(() => {
    setError(false);
  }, [presignedUrl]);

  if (!presignedUrl || error) {
    return (
      <div className="text-center py-8">
        <File size={64} className="text-gray-300 mx-auto mb-3" />
        <p className="text-sm text-gray-500">Image preview not available</p>
      </div>
    );
  }

  return (
    <img
      src={presignedUrl}
      alt={fileName}
      className="max-w-full max-h-[500px] rounded-lg shadow-sm"
      onError={() => setError(true)}
    />
  );
}

// Shared states ─────────────────────────────────────────────────

function PreviewLoading({ label = "Loading preview…" }: { label?: string }) {
  return (
    <div className="w-full text-center py-8">
      <div className="w-6 h-6 border-2 border-otter-600 border-t-transparent rounded-full animate-spin mx-auto" />
      <p className="text-xs text-gray-400 mt-2">{label}</p>
    </div>
  );
}

function PreviewError({ message }: { message: string }) {
  return (
    <div className="text-center py-8">
      <AlertCircle size={48} className="text-gray-300 mx-auto mb-3" />
      <p className="text-sm text-gray-500">{message}</p>
    </div>
  );
}

// Fetch the presigned URL as an ArrayBuffer for client-side parsing (office docs).
function useFileBuffer(presignedUrl?: string) {
  const [buffer, setBuffer] = useState<ArrayBuffer | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (!presignedUrl) {
      setLoading(false);
      setError(true);
      return;
    }
    let cancelled = false;
    setLoading(true);
    setError(false);
    setBuffer(null);
    fetch(presignedUrl)
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const buf = await res.arrayBuffer();
        if (!cancelled) setBuffer(buf);
      })
      .catch(() => {
        if (!cancelled) setError(true);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [presignedUrl]);

  return { buffer, loading, error };
}

// Spreadsheet (xlsx/xls) ─────────────────────────────────────────

interface OfficeFilePreviewProps {
  presignedUrl?: string;
  fileName: string;
}

export function SpreadsheetFilePreview({ presignedUrl, fileName }: OfficeFilePreviewProps) {
  const { buffer, loading, error } = useFileBuffer(presignedUrl);
  const [workbook, setWorkbook] = useState<XLSXWorkBook | null>(null);
  const [sheetNames, setSheetNames] = useState<string[]>([]);
  const [activeSheet, setActiveSheet] = useState(0);
  const [rows, setRows] = useState<string[][]>([]);
  const [truncated, setTruncated] = useState(false);
  const [parseError, setParseError] = useState(false);

  useEffect(() => {
    if (!buffer) return;
    let cancelled = false;
    loadXLSX()
      .then((XLSX) => {
        const wb = XLSX.read(buffer, { type: "array" });
        if (cancelled) return;
        setWorkbook(wb);
        setSheetNames(wb.SheetNames);
        setActiveSheet(0);
      })
      .catch(() => {
        if (!cancelled) setParseError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [buffer]);

  useEffect(() => {
    if (!workbook || sheetNames.length === 0) return;
    let cancelled = false;
    loadXLSX()
      .then((XLSX) => {
        const ws = workbook.Sheets[sheetNames[activeSheet]];
        const data = XLSX.utils.sheet_to_json<string[]>(ws, {
          header: 1,
          blankrows: false,
          defval: "",
          raw: false,
        });
        if (cancelled) return;
        setTruncated(data.length > MAX_SHEET_ROWS);
        setRows(
          data.slice(0, MAX_SHEET_ROWS).map((r) => r.map((c) => (c == null ? "" : String(c))))
        );
      })
      .catch(() => {
        if (!cancelled) setParseError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [workbook, sheetNames, activeSheet]);

  if (loading) return <PreviewLoading label="Loading spreadsheet…" />;
  if (error) return <PreviewError message="Could not load spreadsheet" />;
  if (parseError) return <PreviewError message="Could not read this spreadsheet" />;

  return (
    <div className="w-full">
      {sheetNames.length > 1 && (
        <div className="flex gap-1 mb-2 overflow-x-auto">
          {sheetNames.map((name, i) => (
            <button
              key={name}
              onClick={() => setActiveSheet(i)}
              className={
                "px-3 py-1 text-xs rounded-t-md whitespace-nowrap " +
                (i === activeSheet
                  ? "bg-white border border-gray-200 border-b-white text-gray-900 font-medium"
                  : "bg-gray-100 text-gray-500 hover:bg-gray-200")
              }
            >
              {name}
            </button>
          ))}
        </div>
      )}
      <div className="rounded-lg border border-gray-200 bg-white overflow-auto max-h-[600px]">
        <table className="w-full border-collapse text-sm">
          <tbody>
            {rows.map((row, r) => (
              <tr key={r} className={r === 0 ? "bg-gray-50 font-medium" : "hover:bg-gray-50"}>
                {row.map((cell, c) => (
                  <td
                    key={c}
                    className="border border-gray-100 px-3 py-1 text-gray-800 whitespace-nowrap"
                  >
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="text-xs text-gray-400 mt-2 text-center truncate">{fileName}</p>
      {truncated && (
        <p className="text-xs text-amber-600 mt-1 text-center">
          Showing first {MAX_SHEET_ROWS} rows. Download the file to see all rows.
        </p>
      )}
    </div>
  );
}

// Word document (docx) ───────────────────────────────────────────

export function WordFilePreview({ presignedUrl, fileName }: OfficeFilePreviewProps) {
  const { buffer, loading, error } = useFileBuffer(presignedUrl);
  const [html, setHtml] = useState<string | null>(null);
  const [parseError, setParseError] = useState(false);

  useEffect(() => {
    if (!buffer) return;
    let cancelled = false;
    loadMammoth()
      .then((mod) => (mod.default ?? mod).convertToHtml({ arrayBuffer: buffer }))
      .then((result) => {
        if (!cancelled) setHtml(result.value || "<p><em>(empty document)</em></p>");
      })
      .catch(() => {
        if (!cancelled) setParseError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [buffer]);

  if (loading) return <PreviewLoading label="Loading document…" />;
  if (error) return <PreviewError message="Could not load document" />;
  if (parseError) return <PreviewError message="Could not read this document" />;
  if (html === null) return <PreviewLoading label="Rendering document…" />;

  return (
    <div className="w-full">
      <div className="rounded-lg border border-gray-200 bg-white overflow-auto max-h-[600px] p-6">
        <div
          className="prose prose-sm max-w-none text-gray-800 [&_h1]:font-bold [&_h2]:font-semibold [&_ul]:list-disc [&_ul]:pl-6 [&_ol]:list-decimal [&_ol]:pl-6 [&_table]:border-collapse [&_td]:border [&_td]:border-gray-200 [&_td]:px-2"
          // mammoth output is derived from the document's own content
          dangerouslySetInnerHTML={{ __html: html }}
        />
      </div>
      <p className="text-xs text-gray-400 mt-2 text-center truncate">{fileName}</p>
    </div>
  );
}

// Audio ──────────────────────────────────────────────────────────

export function AudioFilePreview({ presignedUrl, fileName }: OfficeFilePreviewProps) {
  if (!presignedUrl) return <PreviewError message="Audio preview not available" />;
  return (
    <div className="w-full text-center py-6">
      <audio src={presignedUrl} controls className="w-full max-w-md mx-auto">
        <track kind="captions" />
      </audio>
      <p className="text-xs text-gray-400 mt-3 truncate">{fileName}</p>
    </div>
  );
}

// Graceful fallback for types with no dedicated inline renderer ────

interface UnsupportedFilePreviewProps {
  presignedUrl?: string;
  fileName: string;
  size?: number;
  message?: string;
  onDownload?: () => void;
}

export function UnsupportedFilePreview({
  presignedUrl,
  fileName,
  size,
  message = "Inline preview isn't available for this file type.",
  onDownload,
}: UnsupportedFilePreviewProps) {
  return (
    <div className="text-center py-8">
      <FileWarning size={56} className="text-gray-300 mx-auto mb-3" />
      <p className="text-sm font-medium text-gray-700 truncate max-w-xs mx-auto">{fileName}</p>
      {typeof size === "number" && (
        <p className="text-xs text-gray-400 mt-0.5">{formatFileSize(size)}</p>
      )}
      <p className="text-sm text-gray-500 mt-2">{message}</p>
      {(onDownload || presignedUrl) &&
        (onDownload ? (
          <button
            onClick={onDownload}
            className="inline-flex items-center gap-2 mt-4 px-3 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
          >
            <Download size={16} /> Download
          </button>
        ) : (
          <a
            href={presignedUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-2 mt-4 px-3 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
          >
            <Download size={16} /> Download
          </a>
        ))}
    </div>
  );
}
