import type { components } from "@/generated/api";
import { api } from "@/lib/api/client";
import { toApiError } from "@/lib/api/transient";

export type WorkspaceMetrics = components["schemas"]["WorkspaceMetrics"];
export type Period = WorkspaceMetrics["period"];

export const metricsKeys = {
  period: (workspaceId: string, period: Period) => ["metrics", workspaceId, period] as const,
};

export async function fetchMetrics(workspaceId: string, period: Period): Promise<WorkspaceMetrics> {
  const { data, error, response } = await api.GET("/v1/workspaces/{workspace_id}/metrics", {
    params: { path: { workspace_id: workspaceId }, query: { period } },
  });
  if (data === undefined) {
    throw toApiError(response, error);
  }
  return data;
}
