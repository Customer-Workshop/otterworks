import { DEFAULT_PROMPT_TEMPLATE, type Project, type Ticket } from "@/lib/types";

/** Collapse all whitespace (including newlines) into single spaces. */
export function oneLine(s: string): string {
  return s.replace(/\s+/g, " ").trim();
}

/**
 * Render the project's prompt template for a ticket as ONE line. Multi-line
 * prompts render badly in the Devin UI, so every substituted value and the
 * template itself are flattened.
 */
export function renderPrompt(project: Pick<Project, "promptTemplate" | "repo">, ticket: Ticket): string {
  const template = project.promptTemplate?.trim() || DEFAULT_PROMPT_TEMPLATE;
  const vars: Record<string, string> = {
    key: ticket.key,
    title: ticket.title,
    description: ticket.description,
    repo: ticket.repo || project.repo,
    type: ticket.type,
    priority: ticket.priority,
    labels: ticket.labels.join(", "),
    branch: ticket.branch,
  };
  const rendered = template.replace(/\{(\w+)\}/g, (m, name: string) => (name in vars ? oneLine(vars[name] ?? "") : m));
  return oneLine(rendered);
}

/** Absolute callback URL Devin should POST progress to for a ticket. */
export function callbackUrl(publicUrl: string, ticketKey: string): string {
  return `${publicUrl}/api/webhooks/devin?ticket=${encodeURIComponent(ticketKey)}`;
}
