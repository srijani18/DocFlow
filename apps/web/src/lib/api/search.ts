import type { components } from "@/generated/api";
import { api } from "@/lib/api/client";
import { toApiError } from "@/lib/api/transient";

export type SearchResults = components["schemas"]["SearchResults"];
export type SearchHit = components["schemas"]["SearchHit"];

/** What the search box and filter bar hold (F8 AC4). Empty strings mean "any". */
export type SearchParams = {
  q: string;
  doc_type: string;
  status: string;
  vendor: string;
  date_from: string;
  date_to: string;
  amount_min: string;
  amount_max: string;
};

export const EMPTY_SEARCH: SearchParams = {
  q: "",
  doc_type: "",
  status: "",
  vendor: "",
  date_from: "",
  date_to: "",
  amount_min: "",
  amount_max: "",
};

const AMOUNT = /^\d+(\.\d+)?$/;

/** Only the parameters that are set, trimmed: the query string and the cache key. An
 * amount that isn't a number yet (still being typed) is left out. */
export function activeParams(params: SearchParams): Partial<SearchParams> {
  const active: Partial<SearchParams> = {};
  for (const key of Object.keys(params) as (keyof SearchParams)[]) {
    const value = params[key].trim();
    if (value !== "" && (!key.startsWith("amount_") || AMOUNT.test(value))) active[key] = value;
  }
  return active;
}

export function isSearching(params: SearchParams): boolean {
  return Object.keys(activeParams(params)).length > 0;
}

export async function searchDocuments(
  workspaceId: string,
  params: SearchParams,
  cursor: string | null,
): Promise<SearchResults> {
  const { data, error, response } = await api.GET("/v1/workspaces/{workspace_id}/search", {
    params: {
      path: { workspace_id: workspaceId },
      // The API checks the types; the form only collects text.
      query: { ...activeParams(params), ...(cursor ? { cursor } : {}) } as never,
    },
  });
  if (data === undefined) {
    throw toApiError(response, error);
  }
  return data;
}

/** "[[Kaveri]] Fasteners" → [{text: "Kaveri", match: true}, {text: " Fasteners", match: false}]. */
export function snippetParts(snippet: string): { text: string; match: boolean }[] {
  return snippet
    .split(/(\[\[.*?\]\])/)
    .filter((part) => part !== "")
    .map((part) =>
      part.startsWith("[[") && part.endsWith("]]")
        ? { text: part.slice(2, -2), match: true }
        : { text: part, match: false },
    );
}
