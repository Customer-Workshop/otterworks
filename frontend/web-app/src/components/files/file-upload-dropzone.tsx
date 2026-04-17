"use client";

import { useCallback, useState } from "react";
import { useDropzone } from "react-dropzone";
import { Upload, X, FileIcon, CheckCircle2 } from "lucide-react";
import { cn, formatFileSize } from "@/lib/utils";

interface FileUploadDropzoneProps {
  onUpload: (files: File[]) => Promise<void>;
  parentId?: string | null;
  className?: string;
}

interface UploadingFile {
  file: File;
  progress: number;
  status: "uploading" | "done" | "error";
  error?: string;
}

export function FileUploadDropzone({ onUpload, className }: FileUploadDropzoneProps) {
  const [uploadingFiles, setUploadingFiles] = useState<UploadingFile[]>([]);

  const onDrop = useCallback(
    async (acceptedFiles: File[]) => {
      const newFiles = acceptedFiles.map((file) => ({
        file,
        progress: 0,
        status: "uploading" as const,
      }));
      setUploadingFiles((prev) => [...prev, ...newFiles]);

      try {
        await onUpload(acceptedFiles);
        setUploadingFiles((prev) =>
          prev.map((f) =>
            acceptedFiles.includes(f.file) ? { ...f, status: "done" as const, progress: 100 } : f
          )
        );
      } catch {
        setUploadingFiles((prev) =>
          prev.map((f) =>
            acceptedFiles.includes(f.file)
              ? { ...f, status: "error" as const, error: "Upload failed" }
              : f
          )
        );
      }
    },
    [onUpload]
  );

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    multiple: true,
  });

  const clearCompleted = () => {
    setUploadingFiles((prev) => prev.filter((f) => f.status === "uploading"));
  };

  return (
    <div className={className}>
      <div
        {...getRootProps()}
        className={cn(
          "border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition",
          isDragActive
            ? "border-otter-500 bg-otter-50"
            : "border-gray-300 hover:border-otter-400 hover:bg-gray-50"
        )}
      >
        <input {...getInputProps()} />
        <Upload
          size={32}
          className={cn(
            "mx-auto mb-3",
            isDragActive ? "text-otter-600" : "text-gray-400"
          )}
        />
        {isDragActive ? (
          <p className="text-sm text-otter-600 font-medium">Drop files here</p>
        ) : (
          <>
            <p className="text-sm text-gray-600 font-medium">
              Drag & drop files here, or click to browse
            </p>
            <p className="text-xs text-gray-400 mt-1">
              Any file type, up to 100MB per file
            </p>
          </>
        )}
      </div>

      {uploadingFiles.length > 0 && (
        <div className="mt-4 space-y-2">
          <div className="flex items-center justify-between">
            <p className="text-sm font-medium text-gray-700">Uploads</p>
            <button
              onClick={clearCompleted}
              className="text-xs text-gray-500 hover:text-gray-700"
            >
              Clear completed
            </button>
          </div>
          {uploadingFiles.map((item, idx) => (
            <div
              key={idx}
              className="flex items-center gap-3 p-2 bg-white rounded-lg border border-gray-200"
            >
              <FileIcon size={16} className="text-gray-400 flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm text-gray-700 truncate">{item.file.name}</p>
                <p className="text-xs text-gray-400">{formatFileSize(item.file.size)}</p>
              </div>
              {item.status === "done" && (
                <CheckCircle2 size={16} className="text-green-500" />
              )}
              {item.status === "error" && (
                <X size={16} className="text-red-500" />
              )}
              {item.status === "uploading" && (
                <div className="w-4 h-4 border-2 border-otter-600 border-t-transparent rounded-full animate-spin" />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
