import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Megaphone, Send } from "lucide-react";
import toast from "react-hot-toast";
import { AppShell } from "@/components/layout/app-shell";
import { PageLoader } from "@/components/ui/loading-spinner";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorBoundary } from "@/components/ui/error-boundary";
import { formatRelativeTime } from "@/lib/utils";
import { AnnouncementsAlert } from "./alert";
import {
  announcementsApi,
  BODY_MAX_LENGTH,
  TITLE_MAX_LENGTH,
  type Announcement,
} from "./api";

// Mirrors the server-side bean validation exactly; the portal has no other rules.
const announcementSchema = z.object({
  title: z
    .string()
    .trim()
    .min(1, "Title is required")
    .max(TITLE_MAX_LENGTH, `Title must be ${TITLE_MAX_LENGTH} characters or fewer`),
  body: z
    .string()
    .trim()
    .min(1, "Body is required")
    .max(BODY_MAX_LENGTH, `Body must be ${BODY_MAX_LENGTH} characters or fewer`),
  published: z.boolean(),
});

type AnnouncementForm = z.infer<typeof announcementSchema>;

export default function AnnouncementsPage() {
  return (
    <AppShell>
      <ErrorBoundary>
        <AnnouncementsContent />
      </ErrorBoundary>
    </AppShell>
  );
}

export function AnnouncementsContent() {
  const queryClient = useQueryClient();
  const [publishedOnly, setPublishedOnly] = useState(true);
  const [actionError, setActionError] = useState("");
  const [listErrorDismissed, setListErrorDismissed] = useState(false);

  const {
    data: announcements = [],
    isLoading,
    error: listError,
    refetch,
  } = useQuery({
    queryKey: ["announcements", publishedOnly],
    queryFn: () => announcementsApi.list(publishedOnly),
  });

  const retryList = () => {
    setListErrorDismissed(false);
    refetch();
  };

  const {
    register,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<AnnouncementForm>({
    resolver: zodResolver(announcementSchema),
    defaultValues: { title: "", body: "", published: false },
  });

  const createMutation = useMutation({
    mutationFn: (form: AnnouncementForm) => announcementsApi.create(form),
    onSuccess: (created) => {
      setActionError("");
      reset();
      toast.success(`Announcement "${created.title}" created`);
      queryClient.invalidateQueries({ queryKey: ["announcements"] });
    },
    onError: (mutationError: Error) => setActionError(mutationError.message),
  });

  const publishMutation = useMutation({
    mutationFn: (id: number) => announcementsApi.publish(id),
    onSuccess: () => {
      setActionError("");
      queryClient.invalidateQueries({ queryKey: ["announcements"] });
    },
    onError: (mutationError: Error) => setActionError(mutationError.message),
  });

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Announcements</h1>
          <p className="text-sm text-gray-500 mt-1">Portal notices for everyone in the workspace.</p>
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-600">
          <input
            type="checkbox"
            checked={!publishedOnly}
            onChange={(event) => {
              setListErrorDismissed(false);
              setPublishedOnly(!event.target.checked);
            }}
            className="rounded border-gray-300"
          />
          Show unpublished
        </label>
      </div>

      {listError && !listErrorDismissed && (
        <div className="space-y-3">
          <AnnouncementsAlert
            message={listError.message}
            onDismiss={() => setListErrorDismissed(true)}
          />
          <button
            type="button"
            onClick={retryList}
            className="rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm hover:bg-gray-50"
          >
            Retry
          </button>
        </div>
      )}
      {actionError && (
        <AnnouncementsAlert message={actionError} onDismiss={() => setActionError("")} />
      )}

      <form
        className="space-y-4 rounded-xl border border-gray-200 bg-white p-6"
        onSubmit={handleSubmit((form) => createMutation.mutate(form))}
      >
        <h2 className="text-lg font-semibold text-gray-900">New announcement</h2>
        <div>
          <label htmlFor="announcement-title" className="mb-1 block text-sm font-medium text-gray-700">
            Title
          </label>
          <input
            id="announcement-title"
            {...register("title")}
            className="w-full rounded-lg border border-gray-300 px-3 py-2"
          />
          {errors.title && <p className="mt-1 text-sm text-red-600">{errors.title.message}</p>}
        </div>
        <div>
          <label htmlFor="announcement-body" className="mb-1 block text-sm font-medium text-gray-700">
            Body
          </label>
          <textarea
            id="announcement-body"
            rows={4}
            {...register("body")}
            className="w-full rounded-lg border border-gray-300 px-3 py-2"
          />
          {errors.body && <p className="mt-1 text-sm text-red-600">{errors.body.message}</p>}
        </div>
        <label className="flex items-center gap-2 text-sm text-gray-700">
          <input type="checkbox" {...register("published")} className="rounded border-gray-300" />
          Publish immediately
        </label>
        <button
          type="submit"
          disabled={createMutation.isPending}
          className="flex items-center gap-2 rounded-lg bg-otter-600 px-4 py-2 text-sm font-semibold text-white hover:bg-otter-700 disabled:opacity-50"
        >
          <Send size={16} />
          {createMutation.isPending ? "Creating…" : "Create announcement"}
        </button>
      </form>

      {isLoading ? (
        <PageLoader />
      ) : announcements.length === 0 && !listError ? (
        <EmptyState
          icon={Megaphone}
          title="No announcements"
          description={
            publishedOnly
              ? "Nothing has been published yet."
              : "Create the first announcement above."
          }
        />
      ) : (
        <ul className="space-y-3" aria-label="Announcements">
          {announcements.map((announcement) => (
            <AnnouncementRow
              key={announcement.id}
              announcement={announcement}
              isPublishing={
                publishMutation.isPending && publishMutation.variables === announcement.id
              }
              onPublish={() => publishMutation.mutate(announcement.id)}
            />
          ))}
        </ul>
      )}
    </div>
  );
}

function AnnouncementRow({
  announcement,
  isPublishing,
  onPublish,
}: Readonly<{
  announcement: Announcement;
  isPublishing: boolean;
  onPublish: () => void;
}>) {
  return (
    <li className="rounded-xl border border-gray-200 bg-white p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <h3 className="font-semibold text-gray-900">{announcement.title}</h3>
          <p className="mt-1 whitespace-pre-line text-sm text-gray-600">{announcement.body}</p>
          <p className="mt-2 text-xs text-gray-400">
            {formatRelativeTime(announcement.createdAt)}
          </p>
        </div>
        {announcement.published ? (
          <span className="rounded-full bg-green-50 px-3 py-1 text-xs font-semibold text-green-700">
            Published
          </span>
        ) : (
          <button
            type="button"
            onClick={onPublish}
            disabled={isPublishing}
            aria-label={`Publish ${announcement.title}`}
            className="rounded-lg border border-otter-200 bg-otter-50 px-3 py-1 text-sm font-semibold text-otter-700 hover:bg-otter-100 disabled:opacity-50"
          >
            {isPublishing ? "Publishing…" : "Publish"}
          </button>
        )}
      </div>
    </li>
  );
}
