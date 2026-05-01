"use client";

import { useState } from "react";
import { X, Link2, Copy, Check, UserPlus, Globe } from "lucide-react";
import toast from "react-hot-toast";
import { cn } from "@/lib/utils";
import type { SharedUser } from "@/types";

interface ShareDialogProps {
  fileId: string;
  fileName: string;
  sharedWith: SharedUser[];
  resolvedUsers?: Record<string, { name: string; email: string }>;
  onShare: (email: string, permission: "view" | "edit") => Promise<void>;
  onClose: () => void;
}

export function ShareDialog({
  fileId,
  fileName,
  sharedWith,
  resolvedUsers = {},
  onShare,
  onClose,
}: ShareDialogProps) {
  const [email, setEmail] = useState("");
  const [permission, setPermission] = useState<"view" | "edit">("view");
  const [isSharing, setIsSharing] = useState(false);
  const [copied, setCopied] = useState(false);
  const [activeTab, setActiveTab] = useState<"people" | "link">("people");

  const handleShare = async () => {
    if (!email.trim()) return;
    setIsSharing(true);
    try {
      await onShare(email.trim(), permission);
      setEmail("");
      toast.success(`Shared with ${email.trim()}`);
    } catch {
      toast.error("Failed to share file");
    } finally {
      setIsSharing(false);
    }
  };

  const handleCopyLink = async () => {
    const shareUrl = `${window.location.origin}/files/${fileId}`;
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      toast.success("Link copied to clipboard");
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("Failed to copy link");
    }
  };

  return (
    <>
      <div className="fixed inset-0 bg-black/40 z-40" onClick={onClose} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div className="bg-white rounded-2xl shadow-2xl w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
          {/* Header */}
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200">
            <h2 className="text-lg font-semibold text-gray-900">
              Share &ldquo;{fileName}&rdquo;
            </h2>
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition"
            >
              <X size={18} />
            </button>
          </div>

          {/* Tabs */}
          <div className="flex border-b border-gray-200">
            <button
              onClick={() => setActiveTab("people")}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium transition",
                activeTab === "people"
                  ? "text-otter-600 border-b-2 border-otter-600"
                  : "text-gray-500 hover:text-gray-700"
              )}
            >
              <UserPlus size={16} />
              People
            </button>
            <button
              onClick={() => setActiveTab("link")}
              className={cn(
                "flex-1 flex items-center justify-center gap-2 px-4 py-3 text-sm font-medium transition",
                activeTab === "link"
                  ? "text-otter-600 border-b-2 border-otter-600"
                  : "text-gray-500 hover:text-gray-700"
              )}
            >
              <Globe size={16} />
              Get link
            </button>
          </div>

          {/* Content */}
          <div className="px-6 py-5">
            {activeTab === "people" ? (
              <div className="space-y-4">
                {/* Email input + permission */}
                <div className="flex gap-2">
                  <input
                    type="email"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="Add people by email"
                    className="flex-1 px-3.5 py-2.5 border border-gray-300 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-otter-500 focus:border-transparent transition"
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleShare();
                    }}
                  />
                  <select
                    value={permission}
                    onChange={(e) => setPermission(e.target.value as "view" | "edit")}
                    className="px-3 py-2.5 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-otter-500"
                  >
                    <option value="view">Viewer</option>
                    <option value="edit">Editor</option>
                  </select>
                  <button
                    onClick={handleShare}
                    disabled={!email.trim() || isSharing}
                    className="px-4 py-2.5 bg-otter-600 text-white rounded-lg text-sm font-medium hover:bg-otter-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
                  >
                    {isSharing ? "Sharing..." : "Share"}
                  </button>
                </div>

                {/* Shared users list */}
                {sharedWith.length > 0 ? (
                  <div className="space-y-2">
                    <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">
                      People with access
                    </p>
                    {sharedWith.map((user) => {
                      const resolved = resolvedUsers[user.userId];
                      const displayName = resolved?.name || user.name || user.userId.slice(0, 8);
                      const displayEmail = resolved?.email || user.email;
                      return (
                      <div
                        key={user.userId}
                        className="flex items-center justify-between py-2"
                      >
                        <div className="flex items-center gap-3">
                          <div className="w-8 h-8 rounded-full bg-otter-100 flex items-center justify-center text-xs font-medium text-otter-700">
                            {displayName.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <p className="text-sm font-medium text-gray-900">
                              {displayName}
                            </p>
                            <p className="text-xs text-gray-500">{displayEmail}</p>
                          </div>
                        </div>
                        <span className="text-xs text-gray-500 capitalize px-2 py-1 bg-gray-100 rounded-full">
                          {user.permission}
                        </span>
                      </div>
                    );
                    })}
                  </div>
                ) : (
                  <p className="text-sm text-gray-500 text-center py-4">
                    No one else has access yet
                  </p>
                )}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="flex items-center gap-3 p-4 bg-gray-50 rounded-xl">
                  <Link2 size={20} className="text-gray-400 flex-shrink-0" />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-gray-700 truncate">
                      {window.location.origin}/files/{fileId}
                    </p>
                    <p className="text-xs text-gray-500 mt-0.5">
                      Anyone with the link can view this file
                    </p>
                  </div>
                  <button
                    onClick={handleCopyLink}
                    className="flex items-center gap-1.5 px-3 py-2 bg-white border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50 transition flex-shrink-0"
                  >
                    {copied ? (
                      <>
                        <Check size={14} className="text-green-500" />
                        Copied
                      </>
                    ) : (
                      <>
                        <Copy size={14} />
                        Copy link
                      </>
                    )}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
