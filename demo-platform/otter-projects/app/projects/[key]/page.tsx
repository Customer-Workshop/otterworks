import Board from "@/components/Board";

export const dynamic = "force-dynamic";

export default async function ProjectPage({
  params,
  searchParams,
}: {
  params: Promise<{ key: string }>;
  searchParams: Promise<{ ticket?: string }>;
}) {
  const { key } = await params;
  const { ticket } = await searchParams;
  return <Board projectKey={key.toUpperCase()} initialTicket={ticket?.toUpperCase() ?? null} />;
}
