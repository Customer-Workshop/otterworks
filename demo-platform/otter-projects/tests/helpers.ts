import { LocalStore } from "@/lib/store/local";
import { setStore } from "@/lib/store";
import { TicketService } from "@/lib/service";
import type { Project, Ticket } from "@/lib/types";

export function freshStore(): LocalStore {
  const store = new LocalStore("");
  setStore(store);
  return store;
}

export async function seedProject(svc: TicketService, extra: Partial<Project> = {}): Promise<Project> {
  return svc.createProject({ key: "OTTER", name: "OtterWorks", repo: "org/otterworks", dispatcher: "webhook", webhookUrl: "https://hook.test/in", ...extra });
}

export async function seedTicket(svc: TicketService, extra: Record<string, unknown> = {}): Promise<Ticket> {
  return svc.createTicket("OTTER", { title: "Fix the thing", description: "Line one.\nLine two.", type: "bug", priority: "High", ...extra }, "tester");
}

/** fetch mock returning the given responses in order (last one repeats). */
export function fetchQueue(responses: { status: number; body?: unknown; throws?: string }[]) {
  const calls: { url: string; init?: RequestInit }[] = [];
  let i = 0;
  const fn = async (url: string, init?: RequestInit): Promise<Response> => {
    calls.push({ url, init });
    const r = responses[Math.min(i, responses.length - 1)]!;
    i += 1;
    if (r.throws) throw new Error(r.throws);
    return new Response(r.body === undefined ? null : JSON.stringify(r.body), {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    });
  };
  return { fn, calls };
}
