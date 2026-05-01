"use client";

import { useState, useCallback, Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  LayoutGrid,
  List,
  FolderPlus,
  Upload,
  FolderOpen,
} from "lucide-react";
import { AppShell } from "@/components/layout/app-shell";
import { Breadcrumb, type BreadcrumbItem } from "@/components/layout/breadcrumb";
import { FileCard } from "@/components/files/file-card";
import { FolderCard } from "@/components/files/folder-card";
import { FileUploadDropzone } from "@/components/files/file-upload-dropzone";
import { PageLoader } from "@/components/ui/loading-spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { filesApi } from "@/lib/api";
import { useUIStore } from "@/stores/ui-store";
import { cn } from "@/lib/utils";
import type { ViewMode } from "@/types";

function FileBrowserContent() {
  const searchParams = useSearchParams();
  const folderId = searchParams.get("folder");
  const queryClient = useQueryClient();
  const { viewMode, setViewMode } = useUIStore();
  const [showUpload, setShowUpload] = useState(false);
  const [showNewFolder, setShowNewFolder] = useState(false);
  const [newFolderName, setNewFolderName] = useState("");

  const { data, isLoading: filesLoading } = useQuery({
    queryKey: ["files", "list", folderId],
    queryFn: () => filesApi.list(folderId),
  });

  const { data: folderItems, isLoading: foldersLoading } = useQuery({
    queryKey: ["folders", "list", folderId],
    queryFn: () => filesApi.listFolders(folderId),
  });

  const isLoading = filesLoading || foldersLoading;

  const deleteMutation = useMutation({
    mutationFn: filesApi.delete,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["files"] }),
  });

  const deleteFolderMutation = useMutation({
    mutationFn: filesApi.deleteFolder,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["files"] });
      queryClient.invalidateQueries({ queryKey: ["folders"] });
    },
  });

  const createFolderMutation = useMutation({
    mutationFn: (name: string) => filesApi.createFolder(name, folderId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["files"] });
      queryClient.invalidateQueries({ queryKey: ["folders"] });
      setShowNewFolder(false);
      setNewFolderName("");
    },
  });

  const handleUpload = useCallback(
    async (files: File[]) => {
      const results: { file: File; ok: boolean }[] = [];
      for (const file of files) {
        try {
          await filesApi.upload(file, folderId);
          results.push({ file, ok: true });
        } catch {
          results.push({ file, ok: false });
        }
      }
      queryClient.invalidateQueries({ queryKey: ["files"] });
      const failed = results.filter((r) => !r.ok);
      if (failed.length > 0) {
        throw { results };
      }
    },
    [folderId, queryClient]
  );

  const breadcrumbs: BreadcrumbItem[] = [{ label: "Files", href: "/files" }];
  if (folderId) {
    breadcrumbs.push({ label: "Current folder" });
  }

  const folders = folderItems ?? [];
  const files = data?.data ?? [];
  const items = [...folders, ...files];

  return (
    <div className="max-w-7xl mx-auto space-y-6">
      <Breadcrumb items={breadcrumbs} />

      {/* Header */}
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-2xl font-bold text-gray-900">Files</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setShowNewFolder(true)}
            className="flex items-center gap-2 px-3 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
          >
            <FolderPlus size={16} />
            New folder
          </button>
          <button
            onClick={() => setShowUpload(!showUpload)}
            className="flex items-center gap-2 px-3 py-2 text-sm text-white bg-otter-600 rounded-lg hover:bg-otter-700 transition"
          >
            <Upload size={16} />
            Upload
          </button>

          <div className="flex items-center border border-gray-300 rounded-lg overflow-hidden ml-2">
            <ViewModeButton
              mode="grid"
              current={viewMode}
              onClick={() => setViewMode("grid")}
              icon={LayoutGrid}
            />
            <ViewModeButton
              mode="list"
              current={viewMode}
              onClick={() => setViewMode("list")}
              icon={List}
            />
          </div>
        </div>
      </div>

      {/* New folder input */}
      {showNewFolder && (
        <div className="flex items-center gap-2 p-3 bg-white rounded-lg border border-gray-200">
          <FolderPlus size={20} className="text-amber-500" />
          <input
            type="text"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            placeholder="Folder name"
            className="flex-1 px-3 py-1.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-otter-500"
            autoFocus
            onKeyDown={(e) => {
              if (e.key === "Enter" && newFolderName.trim()) {
                createFolderMutation.mutate(newFolderName.trim());
              }
              if (e.key === "Escape") setShowNewFolder(false);
            }}
          />
          <button
            onClick={() => {
              if (newFolderName.trim()) createFolderMutation.mutate(newFolderName.trim());
            }}
            className="px-3 py-1.5 bg-otter-600 text-white rounded-lg text-sm hover:bg-otter-700 transition"
          >
            Create
          </button>
          <button
            onClick={() => setShowNewFolder(false)}
            className="px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg text-sm hover:bg-gray-200 transition"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Upload dropzone */}
      {showUpload && (
        <FileUploadDropzone onUpload={handleUpload} parentId={folderId} />
      )}

      {/* File listing */}
      {isLoading ? (
        <PageLoader />
      ) : items.length === 0 ? (
        <EmptyState
          icon={FolderOpen}
          title="This folder is empty"
          description="Upload files or create folders to get started"
          action={{ label: "Upload files", onClick: () => setShowUpload(true) }}
        />
      ) : (
        <div className="space-y-6">
          {/* Folders */}
          {folders.length > 0 && (
            <section>
              <h2 className="text-sm font-medium text-gray-500 mb-3">Folders</h2>
              <div
                className={cn(
                  viewMode === "grid"
                    ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3"
                    : "space-y-1"
                )}
              >
                {folders.map((folder) => (
                  <FolderCard
                    key={folder.id}
                    folder={folder}
                    view={viewMode}
                    onDelete={(id) => deleteFolderMutation.mutate(id)}
                  />
                ))}
              </div>
            </section>
          )}

          {/* Files */}
          {files.length > 0 && (
            <section>
              <h2 className="text-sm font-medium text-gray-500 mb-3">Files</h2>
              <div
                className={cn(
                  viewMode === "grid"
                    ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3"
                    : "space-y-1"
                )}
              >
                {files.map((file) => (
                  <FileCard
                    key={file.id}
                    file={file}
                    view={viewMode}
                    onDelete={(id) => deleteMutation.mutate(id)}
                  />
                ))}
              </div>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function ViewModeButton({
  mode,
  current,
  onClick,
  icon: Icon,
}: {
  mode: ViewMode;
  current: ViewMode;
  onClick: () => void;
  icon: typeof LayoutGrid;
}) {
  return (
    <button
      onClick={onClick}
      className={cn(
        "p-2 transition",
        mode === current
          ? "bg-gray-100 text-gray-900"
          : "text-gray-400 hover:text-gray-600 hover:bg-gray-50"
      )}
    >
      <Icon size={16} />
    </button>
  );
}

export default function FilesPage() {
  return (
    <AppShell>
      <ErrorBoundary>
        <Suspense fallback={<PageLoader />}>
          <FileBrowserContent />
        </Suspense>
      </ErrorBoundary>
    </AppShell>
  );
}
