import type { components } from "@/generated/api";
import { api } from "@/lib/api/client";
import { toApiError } from "@/lib/api/transient";
import { sha256Hex } from "@/lib/sha256";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

export type DocumentSummary = components["schemas"]["Document"];
type ContentType = components["schemas"]["ContentType"];

export const MAX_UPLOAD_BYTES = 10 * 1024 * 1024;
export const ALLOWED_TYPES: readonly ContentType[] = ["application/pdf", "image/png", "image/jpeg"];
export const ACCEPT = ".pdf,.png,.jpg,.jpeg,application/pdf,image/png,image/jpeg";

export type UploadPhase = "hashing" | "uploading" | "finishing";
export type UploadOutcome =
  { kind: "created"; document: DocumentSummary } | { kind: "duplicate"; document: DocumentSummary };

function isAllowedType(type: string): type is ContentType {
  return (ALLOWED_TYPES as readonly string[]).includes(type);
}

/** Why a file can't be uploaded, or null (F2 AC2). The API and the bucket check again. */
export function validateFile(file: File): string | null {
  if (!isAllowedType(file.type)) {
    return `${file.name} isn't a PDF, PNG or JPEG.`;
  }
  if (file.size === 0) {
    return `${file.name} is empty.`;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    return `${file.name} is larger than 10 MB.`;
  }
  return null;
}

/**
 * Uploads one file (F2 plan §1): hash it, ask the API for a signed upload ticket (or learn
 * it's a duplicate), PUT the bytes straight to Supabase Storage, then complete the upload.
 */
export async function uploadFile(
  workspaceId: string,
  file: File,
  onPhase: (phase: UploadPhase) => void = () => undefined,
): Promise<UploadOutcome> {
  if (!isAllowedType(file.type)) {
    throw new Error(validateFile(file) ?? "Unsupported file type.");
  }
  onPhase("hashing");
  const sha256 = await sha256Hex(file);

  const started = await api.POST("/v1/workspaces/{workspace_id}/uploads", {
    params: { path: { workspace_id: workspaceId } },
    body: { filename: file.name, content_type: file.type, size_bytes: file.size, sha256 },
  });
  if (started.data === undefined) {
    throw toApiError(started.response, started.error);
  }
  if (started.data.kind === "duplicate") {
    return { kind: "duplicate", document: started.data.document };
  }
  const ticket = started.data;

  onPhase("uploading");
  const { error: storageError } = await getSupabaseBrowserClient()
    .storage.from(ticket.bucket)
    .uploadToSignedUrl(ticket.path, ticket.token, file, { contentType: file.type });
  if (storageError) {
    throw new Error("The file couldn't be uploaded. Try again.");
  }

  onPhase("finishing");
  const completed = await api.POST("/v1/workspaces/{workspace_id}/uploads/{upload_id}/complete", {
    params: { path: { workspace_id: workspaceId, upload_id: ticket.upload_id } },
  });
  if (completed.data === undefined) {
    throw toApiError(completed.response, completed.error);
  }
  // 200 means another upload of the same content got there first (F2 AC3, AC5).
  const kind = completed.response.status === 201 ? "created" : "duplicate";
  return { kind, document: completed.data };
}
