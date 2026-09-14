import { redirect } from "next/navigation";

export default async function TicketPage({ params }: { params: Promise<{ key: string; ticket: string }> }) {
  const { key, ticket } = await params;
  redirect(`/projects/${key.toUpperCase()}?ticket=${encodeURIComponent(ticket.toUpperCase())}`);
}
