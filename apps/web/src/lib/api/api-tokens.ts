import type { components } from "@/generated/api";
import { api } from "@/lib/api/client";
import { toApiError } from "@/lib/api/transient";

export type ApiToken = components["schemas"]["ApiToken"];
export type ApiTokenCreated = components["schemas"]["ApiTokenCreated"];
export type ExpiryDays = components["schemas"]["ApiTokenCreate"]["expires_in_days"];

export const apiTokenKeys = { list: (workspaceId: string) => ["api-tokens", workspaceId] as const };

function path(workspaceId: string) {
  return { params: { path: { workspace_id: workspaceId } } };
}

export async function fetchApiTokens(workspaceId: string): Promise<ApiToken[]> {
  const { data, error, response } = await api.GET(
    "/v1/workspaces/{workspace_id}/api-tokens",
    path(workspaceId),
  );
  if (data === undefined) throw toApiError(response, error);
  return data;
}

export async function createApiToken(
  workspaceId: string,
  name: string,
  expiresInDays: ExpiryDays,
): Promise<ApiTokenCreated> {
  const { data, error, response } = await api.POST("/v1/workspaces/{workspace_id}/api-tokens", {
    ...path(workspaceId),
    body: { name, expires_in_days: expiresInDays },
  });
  if (data === undefined) throw toApiError(response, error);
  return data;
}

export async function revokeApiToken(workspaceId: string, tokenId: string): Promise<void> {
  const { error, response } = await api.DELETE(
    "/v1/workspaces/{workspace_id}/api-tokens/{token_id}",
    { params: { path: { workspace_id: workspaceId, token_id: tokenId } } },
  );
  if (!response.ok) throw toApiError(response, error);
}
