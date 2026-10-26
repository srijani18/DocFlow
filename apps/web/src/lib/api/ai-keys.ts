import type { components } from "@/generated/api";
import { api } from "@/lib/api/client";
import { toApiError } from "@/lib/api/transient";

export type AiKeyStatus = components["schemas"]["AiKeyStatus"];
export type Provider = components["schemas"]["Provider"];

export const aiKeyKeys = { list: (workspaceId: string) => ["ai-keys", workspaceId] as const };

export const PROVIDERS: { id: Provider; name: string; blurb: string; keysUrl: string }[] = [
  {
    id: "gemini",
    name: "Google Gemini",
    blurb: "Reads PDFs and images. Recommended as your main provider.",
    keysUrl: "https://aistudio.google.com/apikey",
  },
  {
    id: "groq",
    name: "Groq",
    blurb: "Fast Llama models for images. Used as a fallback.",
    keysUrl: "https://console.groq.com/keys",
  },
  {
    id: "openrouter",
    name: "OpenRouter",
    blurb: "Many models behind one key. Used as a last resort.",
    keysUrl: "https://openrouter.ai/keys",
  },
];

function path(workspaceId: string) {
  return { params: { path: { workspace_id: workspaceId } } };
}

export async function fetchAiKeys(workspaceId: string): Promise<AiKeyStatus[]> {
  const { data, error, response } = await api.GET(
    "/v1/workspaces/{workspace_id}/ai-keys",
    path(workspaceId),
  );
  if (data === undefined) throw toApiError(response, error);
  return data;
}

export async function saveAiKey(
  workspaceId: string,
  provider: Provider,
  apiKey: string,
): Promise<AiKeyStatus> {
  const { data, error, response } = await api.PUT(
    "/v1/workspaces/{workspace_id}/ai-keys/{provider}",
    {
      params: { path: { workspace_id: workspaceId, provider } },
      body: { api_key: apiKey },
    },
  );
  if (data === undefined) throw toApiError(response, error);
  return data;
}

export async function deleteAiKey(workspaceId: string, provider: Provider): Promise<void> {
  const { error, response } = await api.DELETE("/v1/workspaces/{workspace_id}/ai-keys/{provider}", {
    params: { path: { workspace_id: workspaceId, provider } },
  });
  if (!response.ok) throw toApiError(response, error);
}

export async function testAiKey(workspaceId: string, provider: Provider): Promise<AiKeyStatus> {
  const { data, error, response } = await api.POST(
    "/v1/workspaces/{workspace_id}/ai-keys/{provider}/test",
    {
      params: { path: { workspace_id: workspaceId, provider } },
    },
  );
  if (data === undefined) throw toApiError(response, error);
  return data;
}
