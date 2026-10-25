import type { components } from "@/generated/api";

export const WORKSPACE_ID = "0f1e1a3c-6a43-4b6e-9a51-7d0c3c3b8a11";

export function makeDocument(
  overrides: Partial<components["schemas"]["Document"]> = {},
): components["schemas"]["Document"] {
  return {
    id: "8a6e0804-2bd0-4672-b79d-d97027f9a0a1",
    filename: "invoice.pdf",
    content_type: "application/pdf",
    size_bytes: 2048,
    sha256: "a".repeat(64),
    status: "UPLOADED",
    failure_reason: null,
    doc_type: null,
    doc_type_confidence: null,
    status_changed_at: "2026-10-25T10:00:00Z",
    created_at: "2026-10-25T10:00:00Z",
    updated_at: "2026-10-25T10:00:00Z",
    ...overrides,
  };
}
