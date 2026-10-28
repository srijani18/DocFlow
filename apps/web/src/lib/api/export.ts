import { api } from "@/lib/api/client";
import { activeParams, type SearchParams } from "@/lib/api/search";
import { toApiError } from "@/lib/api/transient";

export type ExportFormat = "csv" | "json";

const FALLBACK_NAME = { csv: "docflow-export.zip", json: "docflow-export.json" };

/** The file name from `Content-Disposition: attachment; filename="…"`. */
export function attachmentName(header: string | null, format: ExportFormat): string {
  return header?.match(/filename="([^"]+)"/)?.[1] ?? FALLBACK_NAME[format];
}

/** Fetched with the user's token (a plain link can't carry it), then saved (F9 plan §1). */
export async function exportDocuments(
  workspaceId: string,
  search: SearchParams,
  options: { format: ExportFormat; includeUnapproved: boolean },
): Promise<{ blob: Blob; filename: string }> {
  const { data, error, response } = await api.GET("/v1/workspaces/{workspace_id}/export", {
    params: {
      path: { workspace_id: workspaceId },
      query: {
        ...activeParams(search),
        format: options.format,
        include_unapproved: options.includeUnapproved,
      } as never,
    },
    parseAs: "blob",
  });
  if (data === undefined) {
    throw toApiError(response, error);
  }
  return {
    blob: data as Blob,
    filename: attachmentName(response.headers.get("content-disposition"), options.format),
  };
}

export function saveFile(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}
