import { useQuery } from "@tanstack/react-query";
import { searchApi } from "@/lib/api";
import type { PaginatedResponse, SearchResult } from "@/types";

export interface UseSearchResult {
  data: PaginatedResponse<SearchResult> | undefined;
  results: SearchResult[];
  isLoading: boolean;
}

/**
 * Reusable data-fetching hook for the search experience.
 *
 * Runs the search query against {@link searchApi} whenever a non-empty
 * `query` is supplied, optionally narrowed by `type`. Extracted from
 * `pages/search.tsx` so the fetching logic can be shared and tested in
 * isolation; the behaviour (query key, enablement, result shaping) is
 * intentionally identical to the previous inline implementation.
 */
export function useSearch(query: string, type: string = "all"): UseSearchResult {
  const { data, isLoading } = useQuery({
    queryKey: ["search", query, type],
    queryFn: () =>
      searchApi.search({
        query,
        type: type === "all" ? undefined : (type as "file" | "document" | "folder"),
      }),
    enabled: query.length > 0,
  });

  return { data, results: data?.data || [], isLoading };
}
