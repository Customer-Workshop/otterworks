"use client";

import Link from "next/link";
import {
  File,
  FileText,
  Folder,
  Image,
  Film,
  Music,
  Archive,
  Table,
  MoreVertical,
  Trash2,
  Share2,
  Download,
} from "lucide-react";
import { useState } from "react";
import type { FileItem } from "@/types";
import { formatFileSize, formatRelativeTime } from "@/lib/utils";

const iconMap: Record<string, typeof File> = {
  file: File,
  "file-text": FileText,
  image: Image,
  video: Film,
  music: Music,
  archive: Archive,
  table: Table,
};

function getIconComponent(mimeType: string) {
  if (mimeType.startsWith("image/")) return Image;
  if (mimeType.startsWith("video/")) return Film;
  if (mimeType.startsWith("audio/")) return Music;
  if (mimeType === "application/pdf") return FileText;
  if (mimeType.includes("spreadsheet") || mimeType.includes("excel")) return Table;
  if (mimeType.includes("zip") || mimeType.includes("archive")) return Archive;
  if (mimeType.includes("document") || mimeType.includes("word")) return FileText;
  return File;
}

interface FileCardProps {
  file: FileItem;
  onDelete?: (id: string) => void;
  onShare?: (id: string) => void;
  view?: "grid" | "list";
}

export function FileCard({ file, onDelete, onShare, view = "grid" }: FileCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const Icon = file.isFolder ? Folder : getIconComponent(file.mimeType);

  if (view === "list") {
    return (
      <Link
        href={file.isFolder ? `/files?folder=${file.id}` : `/files/${file.id}`}
        className="flex items-center gap-4 px-4 py-3 hover:bg-gray-50 rounded-lg transition group"
      >
        <div className="w-10 h-10 rounded-lg bg-otter-50 flex items-center justify-center flex-shrink-0">
          <Icon size={20} className="text-otter-600" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">{file.name}</p>
          <p className="text-xs text-gray-500">
            {file.ownerName} &middot; {formatRelativeTime(file.updatedAt)}
          </p>
        </div>
        <span className="text-xs text-gray-400 hidden sm:block">
          {file.isFolder ? "--" : formatFileSize(file.size)}
        </span>
        <div className="relative">
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setMenuOpen(!menuOpen);
            }}
            className="p-1 rounded hover:bg-gray-200 text-gray-400 opacity-0 group-hover:opacity-100 transition"
          >
            <MoreVertical size={16} />
          </button>
          {menuOpen && (
            <FileMenu
              file={file}
              onClose={() => setMenuOpen(false)}
              onDelete={onDelete}
              onShare={onShare}
            />
          )}
        </div>
      </Link>
    );
  }

  return (
    <Link
      href={file.isFolder ? `/files?folder=${file.id}` : `/files/${file.id}`}
      className="group relative flex flex-col rounded-xl border border-gray-200 bg-white hover:shadow-md transition p-4"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="w-12 h-12 rounded-lg bg-otter-50 flex items-center justify-center">
          <Icon size={24} className="text-otter-600" />
        </div>
        <div className="relative">
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              setMenuOpen(!menuOpen);
            }}
            className="p-1 rounded hover:bg-gray-100 text-gray-400 opacity-0 group-hover:opacity-100 transition"
          >
            <MoreVertical size={16} />
          </button>
          {menuOpen && (
            <FileMenu
              file={file}
              onClose={() => setMenuOpen(false)}
              onDelete={onDelete}
              onShare={onShare}
            />
          )}
        </div>
      </div>
      <p className="text-sm font-medium text-gray-900 truncate mb-1">{file.name}</p>
      <p className="text-xs text-gray-500">
        {file.isFolder ? "Folder" : formatFileSize(file.size)}
        {" \u00b7 "}
        {formatRelativeTime(file.updatedAt)}
      </p>
    </Link>
  );
}

function FileMenu({
  file,
  onClose,
  onDelete,
  onShare,
}: {
  file: FileItem;
  onClose: () => void;
  onDelete?: (id: string) => void;
  onShare?: (id: string) => void;
}) {
  return (
    <>
      <div className="fixed inset-0 z-10" onClick={onClose} />
      <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-20">
        {!file.isFolder && (
          <button
            onClick={(e) => {
              e.preventDefault();
              e.stopPropagation();
              onClose();
            }}
            className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
          >
            <Download size={14} />
            Download
          </button>
        )}
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onShare?.(file.id);
            onClose();
          }}
          className="flex items-center gap-2 w-full px-3 py-2 text-sm text-gray-700 hover:bg-gray-50"
        >
          <Share2 size={14} />
          Share
        </button>
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onDelete?.(file.id);
            onClose();
          }}
          className="flex items-center gap-2 w-full px-3 py-2 text-sm text-red-600 hover:bg-red-50"
        >
          <Trash2 size={14} />
          Delete
        </button>
      </div>
    </>
  );
}

// Re-export iconMap for external use
export { iconMap };
