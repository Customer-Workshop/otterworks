import { useState, useEffect, useRef } from "react";
import { File, AlertCircle } from "lucide-react";
import * as XLSX from "xlsx";
import { formatFileSize } from "@/lib/utils";
import {
  MAX_PREVIEW_COLS,
  MAX_PREVIEW_ROWS,
  MAX_TEXT_PREVIEW_BYTES,
  capGrid,
  isPreviewTooLarge,
} from "@/lib/file-preview-utils";

const MAX_PREVIEW_SIZE = MAX_TEXT_PREVIEW_BYTES;

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

interface OfficePreviewProps {
  presignedUrl?: string;
  fileName: string;
  sizeBytes: number;
  mimeType: string;
}

function PreviewSpinner() {
  return (
    <div className="w-full text-center py-8">
      <div className="w-6 h-6 border-2 border-otter-600 border-t-transparent rounded-full animate-spin mx-auto" />
      <p className="text-xs text-gray-400 mt-2">Loading preview…</p>
    </div>
  );
}

function TooLargePreview({
  fileName,
  sizeBytes,
  mimeType,
  presignedUrl,
}: Readonly<{
  fileName: string;
  sizeBytes: number;
  mimeType: string;
  presignedUrl?: string;
}>) {
  return (
    <GenericFilePreview
      fileName={fileName}
      sizeBytes={sizeBytes}
      mimeType={mimeType}
      presignedUrl={presignedUrl}
      message="This file is too large to preview — download it instead."
    />
  );
}

function gridFromSheet(sheet: XLSX.WorkSheet) {
  return capGrid(
    XLSX.utils.sheet_to_json<unknown[]>(sheet, {
      header: 1,
      raw: false,
      defval: "",
    }),
  );
}

export function SpreadsheetFilePreview({
  presignedUrl,
  fileName,
  sizeBytes,
  mimeType,
}: OfficePreviewProps) {
  const [loading, setLoading] = useState(true);
  const [workbook, setWorkbook] = useState<XLSX.WorkBook | null>(null);
  const [rows, setRows] = useState<string[][]>([]);
  const [sheetIndex, setSheetIndex] = useState(0);
  const [truncation, setTruncation] = useState({ rows: false, cols: false });
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(false);
    setWorkbook(null);
    setRows([]);
    setSheetIndex(0);
    setTruncation({ rows: false, cols: false });
    setError(false);

    if (!presignedUrl || isPreviewTooLarge("spreadsheet", sizeBytes)) return;

    let cancelled = false;
    setLoading(true);
    fetch(presignedUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.arrayBuffer();
      })
      .then((buffer) => {
        const parsed = XLSX.read(buffer, { type: "array" });
        const sheet = parsed.Sheets[parsed.SheetNames[0]];
        if (!sheet) throw new Error("Workbook has no sheets");
        const grid = gridFromSheet(sheet);
        if (cancelled) return;
        setWorkbook(parsed);
        setRows(grid.rows);
        setTruncation({ rows: grid.truncatedRows, cols: grid.truncatedCols });
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
  }, [presignedUrl, sizeBytes]);

  if (isPreviewTooLarge("spreadsheet", sizeBytes)) {
    return (
      <TooLargePreview
        fileName={fileName}
        sizeBytes={sizeBytes}
        mimeType={mimeType}
        presignedUrl={presignedUrl}
      />
    );
  }
  if (loading) return <PreviewSpinner />;
  if (!presignedUrl) {
    return (
      <GenericFilePreview
        fileName={fileName}
        sizeBytes={sizeBytes}
        mimeType={mimeType}
      />
    );
  }
  if (error || !workbook) {
    return (
      <GenericFilePreview
        fileName={fileName}
        sizeBytes={sizeBytes}
        mimeType={mimeType}
        presignedUrl={presignedUrl}
        message="Preview unavailable — this file could not be read"
      />
    );
  }

  return (
    <div className="w-full">
      {workbook.SheetNames.length > 1 && (
        <div className="flex gap-1 border-b border-gray-200 mb-3 overflow-x-auto">
          {workbook.SheetNames.map((name, index) => (
            <button
              key={name}
              type="button"
              onClick={() => {
                const sheet = workbook.Sheets[name];
                const grid = gridFromSheet(sheet);
                setSheetIndex(index);
                setRows(grid.rows);
                setTruncation({ rows: grid.truncatedRows, cols: grid.truncatedCols });
              }}
              className={`px-3 py-1.5 text-xs rounded-t ${
                index === sheetIndex
                  ? "bg-white border border-b-white border-gray-200 text-otter-600 font-medium"
                  : "text-gray-500 hover:bg-gray-100"
              }`}
            >
              {name}
            </button>
          ))}
        </div>
      )}
      <div className="rounded-lg border border-gray-200 bg-white overflow-auto max-h-[600px]">
        <table className="w-full border-collapse text-left font-mono text-xs">
          <thead className="sticky top-0 bg-gray-50">
            <tr>
              {(rows[0] ?? []).map((cell, index) => (
                <th key={index} className="px-3 py-2 border-b border-gray-200 font-semibold text-gray-700">
                  {cell}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.slice(1).map((row, rowIndex) => (
              <tr key={rowIndex} className="hover:bg-gray-50">
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="px-3 py-2 border-b border-gray-100 whitespace-nowrap text-gray-700">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {(truncation.rows || truncation.cols) && (
        <p className="text-xs text-amber-600 mt-2 text-center">
          Showing {
            [
              truncation.rows && `the first ${MAX_PREVIEW_ROWS} rows`,
              truncation.cols && `the first ${MAX_PREVIEW_COLS} columns`,
            ]
              .filter(Boolean)
              .join(" and ")
          }.
        </p>
      )}
    </div>
  );
}

export function DocxFilePreview({
  presignedUrl,
  fileName,
  sizeBytes,
  mimeType,
}: OfficePreviewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  useEffect(() => {
    setLoading(false);
    setError(false);
    if (containerRef.current) containerRef.current.innerHTML = "";
    if (!presignedUrl || isPreviewTooLarge("document", sizeBytes)) return;

    let cancelled = false;
    setLoading(true);
    fetch(presignedUrl)
      .then((response) => {
        if (!response.ok) throw new Error(`HTTP ${response.status}`);
        return response.blob();
      })
      .then(async (blob) => {
        const { renderAsync } = await import("docx-preview");
        if (cancelled || !containerRef.current) return;
        await renderAsync(blob, containerRef.current, undefined, {
          inWrapper: false,
          ignoreWidth: true,
          ignoreHeight: true,
        });
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
  }, [presignedUrl, sizeBytes]);

  if (isPreviewTooLarge("document", sizeBytes)) {
    return (
      <TooLargePreview
        fileName={fileName}
        sizeBytes={sizeBytes}
        mimeType={mimeType}
        presignedUrl={presignedUrl}
      />
    );
  }
  if (loading) return <PreviewSpinner />;
  if (!presignedUrl || error) {
    return (
      <GenericFilePreview
        fileName={fileName}
        sizeBytes={sizeBytes}
        mimeType={mimeType}
        presignedUrl={presignedUrl}
        message={error ? "Preview unavailable — this file could not be read" : undefined}
      />
    );
  }

  return (
    <div
      ref={containerRef}
      data-docx-preview
      className="w-full max-h-[600px] overflow-auto rounded-lg border border-gray-200 bg-white p-5"
    />
  );
}

export function AudioFilePreview({
  presignedUrl,
  fileName,
}: Readonly<{ presignedUrl?: string; fileName: string }>) {
  if (!presignedUrl) {
    return (
      <div className="text-center py-8">
        <File size={64} className="text-gray-300 mx-auto mb-3" />
        <p className="text-sm text-gray-500">Audio preview not available</p>
      </div>
    );
  }

  return (
    <div className="w-full space-y-3">
      <p className="text-sm font-medium text-gray-700 truncate">{fileName}</p>
      <audio controls src={presignedUrl} className="w-full">
        Your browser does not support audio playback.
      </audio>
    </div>
  );
}

export function GenericFilePreview({
  fileName,
  sizeBytes,
  mimeType,
  presignedUrl,
  message,
}: Readonly<{
  fileName: string;
  sizeBytes: number;
  mimeType: string;
  presignedUrl?: string;
  message?: string;
}>) {
  return (
    <div className="text-center max-w-md">
      <File size={64} className="text-gray-300 mx-auto mb-3" />
      <p className="text-sm font-medium text-gray-800 break-words">{fileName}</p>
      <p className="text-xs text-gray-500 mt-1">{formatFileSize(sizeBytes)}</p>
      <p className="text-xs text-gray-400 mt-1 break-all">{mimeType}</p>
      {message && <p className="text-sm text-gray-500 mt-3">{message}</p>}
      {presignedUrl && (
        <a
          href={presignedUrl}
          download={fileName}
          className="inline-flex items-center gap-2 px-3 py-2 mt-4 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
        >
          Download
        </a>
      )}
    </div>
  );
}
