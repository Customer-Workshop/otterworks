import { http, HttpResponse } from "msw";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { AnnouncementsContent } from "./announcements-page";
import type { Announcement } from "./api";
import { billingServer } from "../../test-setup";

const LIST_URL = "http://localhost:3000/announcements-api/api/announcements";
const PUBLISH_URL = "http://localhost:3000/announcements-api/api/announcements/:id/publish";

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <AnnouncementsContent />
    </QueryClientProvider>
  );
}

function announcement(overrides: Partial<Announcement> = {}): Announcement {
  return {
    id: 1,
    title: "Scheduled maintenance",
    body: "The portal will be unavailable on Sunday.",
    published: false,
    createdAt: "2026-08-20T20:46:25.637042Z",
    ...overrides,
  };
}

describe("Announcements", () => {
  it("lists published announcements by default and all of them on demand", async () => {
    const requested: (string | null)[] = [];
    billingServer.use(
      http.get(LIST_URL, ({ request }) => {
        const publishedOnly = new URL(request.url).searchParams.get("publishedOnly");
        requested.push(publishedOnly);
        return HttpResponse.json(
          publishedOnly === "false"
            ? [announcement(), announcement({ id: 2, title: "Release 4.2", published: true })]
            : [announcement({ id: 2, title: "Release 4.2", published: true })]
        );
      })
    );
    renderPage();

    expect(await screen.findByText("Release 4.2")).toBeInTheDocument();
    expect(screen.queryByText("Scheduled maintenance")).not.toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Show unpublished"));

    expect(await screen.findByText("Scheduled maintenance")).toBeInTheDocument();
    await waitFor(() => expect(requested).toEqual(["true", "false"]));
  });

  it("creates an announcement and shows it in the list without a reload", async () => {
    const created: unknown[] = [];
    billingServer.use(
      http.get(LIST_URL, () =>
        HttpResponse.json(
          created.length === 0 ? [] : [announcement({ id: 7, title: "Otter fest", published: true })]
        )
      ),
      http.post(LIST_URL, async ({ request }) => {
        created.push(await request.json());
        return HttpResponse.json(
          announcement({ id: 7, title: "Otter fest", published: true }),
          { status: 201 }
        );
      })
    );
    renderPage();
    await screen.findByText("No announcements");

    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Otter fest" } });
    fireEvent.change(screen.getByLabelText("Body"), { target: { value: "Bring your own fish." } });
    fireEvent.click(screen.getByLabelText("Publish immediately"));
    fireEvent.click(screen.getByRole("button", { name: /Create announcement/ }));

    expect(await screen.findByText("Otter fest")).toBeInTheDocument();
    expect(created).toEqual([
      { title: "Otter fest", body: "Bring your own fish.", published: true },
    ]);
  });

  it("rejects a blank title and an over-long body without calling the server", async () => {
    let posts = 0;
    billingServer.use(
      http.get(LIST_URL, () => HttpResponse.json([])),
      http.post(LIST_URL, () => {
        posts += 1;
        return HttpResponse.json(announcement(), { status: 201 });
      })
    );
    renderPage();
    await screen.findByText("No announcements");

    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "   " } });
    fireEvent.change(screen.getByLabelText("Body"), { target: { value: "x".repeat(4001) } });
    fireEvent.click(screen.getByRole("button", { name: /Create announcement/ }));

    expect(await screen.findByText("Title is required")).toBeInTheDocument();
    expect(screen.getByText("Body must be 4000 characters or fewer")).toBeInTheDocument();
    expect(posts).toBe(0);
  });

  it("publishes an announcement and reflects it in the list without a reload", async () => {
    let published = false;
    billingServer.use(
      http.get(LIST_URL, ({ request }) => {
        const publishedOnly = new URL(request.url).searchParams.get("publishedOnly");
        if (publishedOnly === "false") {
          return HttpResponse.json([announcement({ published })]);
        }
        return HttpResponse.json(published ? [announcement({ published: true })] : []);
      }),
      http.post(PUBLISH_URL, () => {
        published = true;
        return HttpResponse.json(announcement({ published: true }));
      })
    );
    renderPage();
    await screen.findByText("No announcements");

    fireEvent.click(screen.getByLabelText("Show unpublished"));
    const row = (await screen.findByText("Scheduled maintenance")).closest("li") as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "Publish Scheduled maintenance" }));

    expect(await screen.findByText("Published")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Publish Scheduled maintenance" })
    ).not.toBeInTheDocument();
  });

  it("surfaces the legacy error envelope's message", async () => {
    billingServer.use(
      http.get(LIST_URL, () =>
        HttpResponse.json(
          { error: "Bad Request", message: "Invalid boolean value [maybe]" },
          { status: 400 }
        )
      )
    );
    renderPage();

    expect(await screen.findByRole("alert")).toHaveTextContent("Invalid boolean value [maybe]");
  });

  it("surfaces the default error envelope, which carries no message", async () => {
    billingServer.use(
      http.get(LIST_URL, () => HttpResponse.json([])),
      http.post(LIST_URL, () =>
        HttpResponse.json(
          {
            timestamp: "2026-08-20T20:46:25.772+00:00",
            status: 400,
            error: "Bad Request",
            path: "/api/announcements",
          },
          { status: 400 }
        )
      )
    );
    renderPage();
    await screen.findByText("No announcements");

    fireEvent.change(screen.getByLabelText("Title"), { target: { value: "Otter fest" } });
    fireEvent.change(screen.getByLabelText("Body"), { target: { value: "Bring your own fish." } });
    fireEvent.click(screen.getByRole("button", { name: /Create announcement/ }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Bad Request");
  });
});
