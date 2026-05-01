"use client";

import Link from "next/link";
import { Folder, MoreVertical, Trash2, Share2 } from "lucide-react";
import { useState } from "react";
import type { FileItem } from "@/types";
import { formatRelativeTime } from "@/lib/utils";

interface FolderCardProps {
  folder: FileItem;
  onDelete?: (id: string) => void;
  onShare?: (id: string) => void;
  view?: "grid" | "list";
}

export function FolderCard({ folder, onDelete, onShare, view = "grid" }: FolderCardProps) {
  const [menuOpen, setMenuOpen] = useState(false);

  if (view === "list") {
    return (
      <Link
        href={`/files?folder=${folder.id}`}
        className="flex items-center gap-4 px-4 py-2.5 hover:bg-gray-50 rounded-lg transition group border-b border-gray-100 last:border-0"
      >
        <div className="w-10 h-10 rounded-lg bg-amber-50 flex items-center justify-center flex-shrink-0">
          <Folder size={20} className="text-amber-600" />
        </div>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-900 truncate">{folder.name}</p>
        </div>
        <span className="text-xs text-gray-500 w-32 hidden sm:block truncate">
          {formatRelativeTime(folder.updatedAt)}
        </span>
        <span className="text-xs text-gray-400 w-20 hidden sm:block text-right">&mdash;</span>
        <div className="relative w-8">
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
            <FolderMenu
              folder={folder}
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
      href={`/files?folder=${folder.id}`}
      className="group relative flex flex-col rounded-xl border border-gray-200 bg-white hover:shadow-md transition p-4"
    >
      <div className="flex items-start justify-between mb-3">
        <div className="w-12 h-12 rounded-lg bg-amber-50 flex items-center justify-center">
          <Folder size={24} className="text-amber-600" />
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
            <FolderMenu
              folder={folder}
              onClose={() => setMenuOpen(false)}
              onDelete={onDelete}
              onShare={onShare}
            />
          )}
        </div>
      </div>
      <p className="text-sm font-medium text-gray-900 truncate mb-1">{folder.name}</p>
      <p className="text-xs text-gray-500">
        Folder &middot; {formatRelativeTime(folder.updatedAt)}
      </p>
    </Link>
  );
}

function FolderMenu({
  folder,
  onClose,
  onDelete,
  onShare,
}: {
  folder: FileItem;
  onClose: () => void;
  onDelete?: (id: string) => void;
  onShare?: (id: string) => void;
}) {
  return (
    <>
      <div className="fixed inset-0 z-10" onClick={onClose} />
      <div className="absolute right-0 top-full mt-1 w-40 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-20">
        <button
          onClick={(e) => {
            e.preventDefault();
            e.stopPropagation();
            onShare?.(folder.id);
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
            onDelete?.(folder.id);
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
