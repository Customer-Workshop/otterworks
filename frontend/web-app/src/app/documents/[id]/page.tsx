"use client";

import { useParams, useRouter } from "next/navigation";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState, useRef, useCallback, useEffect } from "react";
import {
  ArrowLeft,
  Share2,
  Trash2,
  Save,
  Clock,
  Users,
} from "lucide-react";
import Link from "next/link";
import { AppShell } from "@/components/layout/app-shell";
import { Breadcrumb } from "@/components/layout/breadcrumb";
import { CollaborativeEditor } from "@/components/editor/collaborative-editor";
import { UserPresenceAvatars } from "@/components/editor/user-presence-avatars";
import { PageLoader } from "@/components/ui/loading-spinner";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { documentsApi } from "@/lib/api";
import { formatRelativeTime } from "@/lib/utils";

export default function DocumentEditorPage() {
  return (
    <AppShell>
      <ErrorBoundary>
        <DocumentEditorContent />
      </ErrorBoundary>
    </AppShell>
  );
}

function DocumentEditorContent() {
  const params = useParams();
  const router = useRouter();
  const queryClient = useQueryClient();
  const documentId = params.id as string;
  const [title, setTitle] = useState("");
  const [isTitleEditing, setIsTitleEditing] = useState(false);
  const latestContentRef = useRef<string | null>(null);
  const editorHasUpdated = useRef(false);
  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { data: document, isLoading } = useQuery({
    queryKey: ["documents", documentId],
    queryFn: () => documentsApi.get(documentId),
  });

  const updateMutation = useMutation({
    mutationFn: (updates: { title?: string; content?: string }) =>
      documentsApi.update(documentId, updates),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents", documentId] });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: () => documentsApi.delete(documentId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
      router.push("/documents");
    },
  });

  useEffect(() => {
    if (document?.content && latestContentRef.current === null) {
      latestContentRef.current = document.content;
    }
  }, [document]);

  const debouncedSave = useCallback(
    (content: string) => {
      latestContentRef.current = content;
      editorHasUpdated.current = true;
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
      saveTimerRef.current = setTimeout(() => {
        updateMutation.mutate({ content });
      }, 1000);
    },
    [updateMutation]
  );

  useEffect(() => {
    return () => {
      if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    };
  }, []);

  if (isLoading) return <PageLoader />;
  if (!document) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[400px]">
        <p className="text-gray-500">Document not found</p>
        <Link href="/documents" className="text-otter-600 hover:underline mt-2 text-sm">
          Back to documents
        </Link>
      </div>
    );
  }

  const displayTitle = isTitleEditing ? title : document.title;

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <Breadcrumb
        items={[
          { label: "Documents", href: "/documents" },
          { label: document.title },
        ]}
      />

      {/* Header */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3 flex-1 min-w-0">
          <button
            onClick={() => router.back()}
            className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 flex-shrink-0"
          >
            <ArrowLeft size={20} />
          </button>
          {isTitleEditing ? (
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              onBlur={() => {
                if (title.trim() && title !== document.title) {
                  updateMutation.mutate({ title: title.trim() });
                }
                setIsTitleEditing(false);
              }}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  (e.target as HTMLInputElement).blur();
                }
              }}
              className="text-xl font-bold text-gray-900 bg-transparent border-b-2 border-otter-500 outline-none flex-1 min-w-0"
              autoFocus
            />
          ) : (
            <h1
              className="text-xl font-bold text-gray-900 cursor-pointer hover:text-otter-700 truncate"
              onClick={() => {
                setTitle(document.title);
                setIsTitleEditing(true);
              }}
              title="Click to rename"
            >
              {displayTitle}
            </h1>
          )}
        </div>

        <div className="flex items-center gap-3">
          {/* Collaborators */}
          {document.collaborators.length > 0 && (
            <UserPresenceAvatars collaborators={document.collaborators} />
          )}

          <div className="flex items-center gap-2">
            <button
              onClick={() => {
                if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
                if (latestContentRef.current !== null) {
                  updateMutation.mutate({ content: latestContentRef.current });
                }
              }}
              disabled={updateMutation.isPending || latestContentRef.current === null}
              className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition"
            >
              <Save size={16} />
              Save
            </button>
            <button className="flex items-center gap-1.5 px-3 py-2 text-sm text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition">
              <Share2 size={16} />
              Share
            </button>
            <button
              onClick={() => deleteMutation.mutate()}
              className="flex items-center gap-1.5 px-3 py-2 text-sm text-red-600 bg-white border border-red-200 rounded-lg hover:bg-red-50 transition"
            >
              <Trash2 size={16} />
            </button>
          </div>
        </div>
      </div>

      {/* Meta info */}
      <div className="flex items-center gap-4 text-xs text-gray-400">
        <span className="flex items-center gap-1">
          <Clock size={12} />
          Last edited {formatRelativeTime(document.updatedAt)}
        </span>
        <span className="flex items-center gap-1">
          <Users size={12} />
          {document.collaborators.filter((c) => c.isOnline).length} online
        </span>
        {document.wordCount > 0 && (
          <span>{document.wordCount} words</span>
        )}
      </div>

      {/* Editor */}
      <CollaborativeEditor
        documentId={documentId}
        onUpdate={debouncedSave}
      />
    </div>
  );
}
