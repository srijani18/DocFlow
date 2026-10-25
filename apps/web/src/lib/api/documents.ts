import type { components } from "@/generated/api";
import { api } from "@/lib/api/client";
import { toApiError } from "@/lib/api/transient";

export type DocumentSummary = components["schemas"]["Document"];
export type DocumentPage = components["schemas"]["DocumentPage"];

export const documentKeys = {
  list: (workspaceId: string) => ["documents", workspaceId] as const,
  detail: (workspaceId: string, documentId: string) =>
    ["documents", workspaceId, "detail", documentId] as const,
};

export async function fetchDocumentPage(
  workspaceId: string,
  cursor: string | null,
): Promise<DocumentPage> {
  const { data, error, response } = await api.GET("/v1/workspaces/{workspace_id}/documents", {
    params: { path: { workspace_id: workspaceId }, query: cursor ? { cursor } : {} },
  });
  if (data === undefined) {
    throw toApiError(response, error);
  }
  return data;
}

export async function fetchDocument(
  workspaceId: string,
  documentId: string,
): Promise<DocumentSummary> {
  const { data, error, response } = await api.GET(
    "/v1/workspaces/{workspace_id}/documents/{document_id}",
    { params: { path: { workspace_id: workspaceId, document_id: documentId } } },
  );
  if (data === undefined) {
    throw toApiError(response, error);
  }
  return data;
}

export async function fetchFileUrl(workspaceId: string, documentId: string): Promise<string> {
  const { data, error, response } = await api.POST(
    "/v1/workspaces/{workspace_id}/documents/{document_id}/file-url",
    { params: { path: { workspace_id: workspaceId, document_id: documentId } } },
  );
  if (data === undefined) {
    throw toApiError(response, error);
  }
  return data.url;
}
