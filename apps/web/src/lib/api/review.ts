import type { components } from "@/generated/api";
import { api } from "@/lib/api/client";
import type { DocumentSummary, Extraction } from "@/lib/api/documents";
import { toApiError } from "@/lib/api/transient";

export type ReviewMetrics = components["schemas"]["ReviewMetrics"];

export async function fetchSchema(schemaId: string): Promise<Record<string, unknown>> {
  const { data, error, response } = await api.GET("/v1/schemas/{schema_id}", {
    params: { path: { schema_id: schemaId } },
  });
  if (data === undefined) {
    throw toApiError(response, error);
  }
  return data;
}

export async function saveCorrections(
  workspaceId: string,
  documentId: string,
  baseVersion: number,
  data: Record<string, unknown>,
): Promise<Extraction> {
  const {
    data: saved,
    error,
    response,
  } = await api.PUT("/v1/workspaces/{workspace_id}/documents/{document_id}/extraction", {
    params: { path: { workspace_id: workspaceId, document_id: documentId } },
    body: { base_version: baseVersion, data },
  });
  if (saved === undefined) {
    throw toApiError(response, error);
  }
  return saved;
}

export async function approveDocument(
  workspaceId: string,
  documentId: string,
  body: { version: number; data: Record<string, unknown> | null; accept_errors: boolean },
): Promise<DocumentSummary> {
  const { data, error, response } = await api.POST(
    "/v1/workspaces/{workspace_id}/documents/{document_id}/approve",
    { params: { path: { workspace_id: workspaceId, document_id: documentId } }, body },
  );
  if (data === undefined) {
    throw toApiError(response, error);
  }
  return data;
}

export async function fetchReviewMetrics(workspaceId: string): Promise<ReviewMetrics> {
  const { data, error, response } = await api.GET("/v1/workspaces/{workspace_id}/metrics/review", {
    params: { path: { workspace_id: workspaceId } },
  });
  if (data === undefined) {
    throw toApiError(response, error);
  }
  return data;
}
