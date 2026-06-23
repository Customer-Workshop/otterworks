"use client";

import { useState } from "react";
import { X, FolderOpen, Home } from "lucide-react";
import { cn } from "@/lib/utils";
import type { FileItem } from "@/types";

interface MoveDialogProps {
  folders: FileItem[];
  currentFolderId: string | null;
  onMove: (targetFolderId: string | null) => void;
  onClose: () => void;
}

export function MoveDialog({ folders, currentFolderId, onMove, onClose }: MoveDialogProps) {
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm">
      <div className="bg-white rounded-xl shadow-2xl border border-gray-200 w-full max-w-md mx-4">
        <div className="flex items-center justify-between p-4 border-b border-gray-200">
          <h2 className="text-lg font-semibold text-gray-900">Move to folder</h2>
          <button
            onClick={onClose}
            className="p-1 text-gray-400 hover:text-gray-600 rounded-lg hover:bg-gray-100 transition"
            aria-label="Close move dialog"
          >
            <X size={20} />
          </button>
        </div>
        <div className="p-4 max-h-64 overflow-y-auto space-y-1">
          <button
            onClick={() => setSelectedFolderId(null)}
            className={cn(
              "flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm transition",
              selectedFolderId === null && currentFolderId !== null
                ? "bg-otter-50 text-otter-800 border border-otter-200"
                : "text-gray-700 hover:bg-gray-50"
            )}
          >
            <Home size={16} className="text-gray-400" />
            Root (My Files)
          </button>
          {folders
            .filter((f) => f.id !== currentFolderId)
            .map((folder) => (
              <button
                key={folder.id}
                onClick={() => setSelectedFolderId(folder.id)}
                className={cn(
                  "flex items-center gap-3 w-full px-3 py-2.5 rounded-lg text-sm transition",
                  selectedFolderId === folder.id
                    ? "bg-otter-50 text-otter-800 border border-otter-200"
                    : "text-gray-700 hover:bg-gray-50"
                )}
              >
                <FolderOpen size={16} className="text-amber-500" />
                {folder.name}
              </button>
            ))}
          {folders.length === 0 && (
            <p className="text-sm text-gray-500 text-center py-4">No folders available</p>
          )}
        </div>
        <div className="flex items-center justify-end gap-2 p-4 border-t border-gray-200">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm text-gray-700 bg-gray-100 rounded-lg hover:bg-gray-200 transition"
          >
            Cancel
          </button>
          <button
            onClick={() => onMove(selectedFolderId)}
            className="px-4 py-2 text-sm text-white bg-otter-600 rounded-lg hover:bg-otter-700 transition"
          >
            Move here
          </button>
        </div>
      </div>
    </div>
  );
}
