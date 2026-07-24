import { useEffect } from "react";
import { useQuery } from "@tanstack/react-query";
import { X, Download } from "lucide-react";
import type { FileItem } from "@/types";
import { filesApi } from "@/lib/api";
import { getPreviewKind } from "@/lib/file-preview";
import {
  TextFilePreview,
  PdfFilePreview,
  ImageFilePreview,
  SpreadsheetFilePreview,
  WordFilePreview,
  AudioFilePreview,
  UnsupportedFilePreview,
} from "@/components/files/file-preview";

interface FilePreviewModalProps {
  file: FileItem;
  onClose: () => void;
}

// Quick-look preview modal opened from the file list — renders the file inline
// (no navigation, no download) based on its MIME type.
export function FilePreviewModal({ file, onClose }: FilePreviewModalProps) {
  const { data: previewUrl, isLoading } = useQuery({
    queryKey: ["files", file.id, "preview-url"],
    queryFn: () => filesApi.getPreviewUrl(file.id),
    staleTime: 30 * 60 * 1000,
  });

  // Close on Escape and via the browser Back button (push a history entry so
  // Back pops the modal instead of leaving the page).
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    window.history.pushState({ preview: file.id }, "");
    const onPop = () => onClose();
    window.addEventListener("popstate", onPop);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("popstate", onPop);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [file.id]);

  const handleDownload = async () => {
    try {
      const url = await filesApi.getDownloadUrl(file.id);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.name;
      a.rel = "noopener";
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch {
      /* no-op: download is a secondary action here */
    }
  };

  const kind = getPreviewKind(file.mimeType, file.name);

  const renderBody = () => {
    if (isLoading) {
      return (
        <div className="w-full text-center py-12">
          <div className="w-6 h-6 border-2 border-otter-600 border-t-transparent rounded-full animate-spin mx-auto" />
          <p className="text-xs text-gray-400 mt-2">Loading preview…</p>
        </div>
      );
    }
    switch (kind) {
      case "image":
        return <ImageFilePreview presignedUrl={previewUrl} fileName={file.name} />;
      case "video":
        return previewUrl ? (
          <video src={previewUrl} controls className="max-w-full max-h-[70vh] rounded-lg mx-auto">
            <track kind="captions" />
          </video>
        ) : (
          <UnsupportedFilePreview fileName={file.name} size={file.size} onDownload={handleDownload} />
        );
      case "audio":
        return <AudioFilePreview presignedUrl={previewUrl} fileName={file.name} />;
      case "pdf":
        return <PdfFilePreview presignedUrl={previewUrl} />;
      case "text":
        return <TextFilePreview presignedUrl={previewUrl} fileName={file.name} />;
      case "spreadsheet":
        return <SpreadsheetFilePreview presignedUrl={previewUrl} fileName={file.name} />;
      case "word":
        return <WordFilePreview presignedUrl={previewUrl} fileName={file.name} />;
      case "presentation":
        return (
          <UnsupportedFilePreview
            fileName={file.name}
            size={file.size}
            message="Inline preview isn't available for PowerPoint files yet. Download to view."
            onDownload={handleDownload}
          />
        );
      default:
        return (
          <UnsupportedFilePreview fileName={file.name} size={file.size} onDownload={handleDownload} />
        );
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label={`Preview of ${file.name}`}
    >
      <div
        className="bg-white rounded-xl shadow-2xl w-full max-w-4xl max-h-[90vh] flex flex-col"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between gap-4 px-5 py-3 border-b border-gray-200">
          <h2 className="text-sm font-semibold text-gray-900 truncate">{file.name}</h2>
          <div className="flex items-center gap-2 flex-shrink-0">
            <button
              onClick={handleDownload}
              className="flex items-center gap-1.5 px-2.5 py-1.5 text-xs text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
            >
              <Download size={14} /> Download
            </button>
            <button
              onClick={onClose}
              aria-label="Close preview"
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
            >
              <X size={18} />
            </button>
          </div>
        </div>
        <div className="p-6 overflow-auto bg-gray-50 flex-1 flex items-center justify-center">
          <div className="w-full">{renderBody()}</div>
        </div>
      </div>
    </div>
  );
}
