"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useQuery } from "@tanstack/react-query";
import { Folder, FolderOpen, Home } from "lucide-react";
import { filesApi } from "@/lib/api";
import { cn } from "@/lib/utils";

interface FolderPickerDialogProps {
  currentFolderId?: string | null;
  onSelect: (folderId: string | null) => void;
  onClose: () => void;
}

export function FolderPickerDialog({
  currentFolderId,
  onSelect,
  onClose,
}: FolderPickerDialogProps) {
  const [selectedFolderId, setSelectedFolderId] = useState<string | null>(null);
  const dialogRef = useRef<HTMLDivElement>(null);

  const { data: folders, isLoading } = useQuery({
    queryKey: ["folders", "picker"],
    queryFn: () => filesApi.listFolders(null),
  });

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    },
    [onClose],
  );

  useEffect(() => {
    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  const folderList = (folders ?? []).filter((f) => f.id !== currentFolderId);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center"
      role="dialog"
      aria-modal="true"
      aria-labelledby="folder-picker-title"
    >
      <div
        className="fixed inset-0 bg-black/50 transition-opacity"
        onClick={onClose}
        aria-hidden="true"
      />

      <div
        ref={dialogRef}
        className="relative bg-white rounded-xl shadow-xl max-w-md w-full mx-4 p-6 space-y-4"
      >
        <h2
          id="folder-picker-title"
          className="text-lg font-semibold text-gray-900"
        >
          Move to folder
        </h2>

        <div className="max-h-64 overflow-y-auto space-y-1">
          <button
            onClick={() => setSelectedFolderId(null)}
            className={cn(
              "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition",
              selectedFolderId === null
                ? "bg-otter-50 text-otter-800 border border-otter-200"
                : "text-gray-700 hover:bg-gray-50",
            )}
          >
            <Home size={18} className="flex-shrink-0" />
            <span className="truncate">Root (no folder)</span>
          </button>

          {isLoading ? (
            <div className="px-3 py-4 text-sm text-gray-500 text-center">
              Loading folders...
            </div>
          ) : folderList.length === 0 ? (
            <div className="px-3 py-4 text-sm text-gray-500 text-center">
              No other folders available
            </div>
          ) : (
            folderList.map((folder) => (
              <button
                key={folder.id}
                onClick={() => setSelectedFolderId(folder.id)}
                className={cn(
                  "w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm transition",
                  selectedFolderId === folder.id
                    ? "bg-otter-50 text-otter-800 border border-otter-200"
                    : "text-gray-700 hover:bg-gray-50",
                )}
              >
                {selectedFolderId === folder.id ? (
                  <FolderOpen size={18} className="text-amber-500 flex-shrink-0" />
                ) : (
                  <Folder size={18} className="text-amber-500 flex-shrink-0" />
                )}
                <span className="truncate">{folder.name}</span>
              </button>
            ))
          )}
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button
            onClick={onClose}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
          >
            Cancel
          </button>
          <button
            onClick={() => onSelect(selectedFolderId)}
            className="px-4 py-2 text-sm font-medium text-white bg-otter-600 rounded-lg hover:bg-otter-700 transition"
          >
            Move here
          </button>
        </div>
      </div>
    </div>
  );
}
