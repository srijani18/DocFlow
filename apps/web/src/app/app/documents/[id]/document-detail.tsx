"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";

import { DocTypeLabel, OTHER_NOTE } from "@/components/doc-type";
import { DocumentStatusBadge } from "@/components/document-status";
import { MeGate } from "@/components/me-gate";
import { Button } from "@/components/ui/button";
import { useDocumentEvents } from "@/hooks/use-document-events";
import { documentKeys, fetchDocument, fetchFileUrl, retryDocument } from "@/lib/api/documents";
import { currentWorkspace } from "@/lib/api/me";
import { ApiError } from "@/lib/api/transient";
import { formatBytes, formatDateTime } from "@/lib/format";

export function DocumentDetailView() {
  const { id } = useParams<{ id: string }>();
  return (
    <MeGate>
      {(me) => {
        const membership = currentWorkspace(me);
        if (membership === undefined) {
          return <p className="text-sm">You don&apos;t belong to a workspace yet.</p>;
        }
        return <DocumentDetail workspaceId={membership.workspace.id} documentId={id} />;
      }}
    </MeGate>
  );
}

/** One document's details and a link to the original file (F2 AC9). */
export function DocumentDetail({
  workspaceId,
  documentId,
}: {
  workspaceId: string;
  documentId: string;
}) {
  const queryClient = useQueryClient();
  useDocumentEvents(workspaceId);
  const document = useQuery({
    queryKey: documentKeys.detail(workspaceId, documentId),
    queryFn: () => fetchDocument(workspaceId, documentId),
    retry: (count, error) => !(error instanceof ApiError && error.status === 404) && count < 2,
  });
  // The link is minted on click and expires after 5 minutes, so it's never cached.
  const openOriginal = useMutation({
    mutationFn: () => fetchFileUrl(workspaceId, documentId),
    onSuccess: (url) => window.open(url, "_blank", "noopener,noreferrer"),
  });

  // Queue the document again with fresh attempts (F3 AC8); live events show its progress.
  const retry = useMutation({
    mutationFn: () => retryDocument(workspaceId, documentId),
    onSuccess: (updated) => {
      queryClient.setQueryData(documentKeys.detail(workspaceId, documentId), updated);
      void queryClient.invalidateQueries({ queryKey: documentKeys.list(workspaceId) });
    },
  });

  if (document.isPending) {
    return <p className="text-sm text-muted-foreground">Loading document…</p>;
  }
  if (document.isError) {
    const notFound = document.error instanceof ApiError && document.error.status === 404;
    return (
      <div role="alert" className="flex flex-col items-start gap-2 text-sm">
        {notFound ? "Document not found." : "Couldn't load this document."}
        <Link href="/app/documents" className="underline underline-offset-4">
          Back to documents
        </Link>
      </div>
    );
  }
  const doc = document.data;
  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center gap-3">
        <h2 className="text-xl font-semibold break-all">{doc.filename}</h2>
        <DocumentStatusBadge status={doc.status} />
      </div>
      {doc.doc_type === "other" && (
        <p className="rounded-md border px-3 py-2 text-sm">{OTHER_NOTE}.</p>
      )}
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Document type</dt>
        <dd>
          <DocTypeLabel docType={doc.doc_type} confidence={doc.doc_type_confidence} />
        </dd>
        <dt className="text-muted-foreground">File type</dt>
        <dd>{doc.content_type}</dd>
        <dt className="text-muted-foreground">Size</dt>
        <dd>{formatBytes(doc.size_bytes)}</dd>
        <dt className="text-muted-foreground">Uploaded</dt>
        <dd>{formatDateTime(doc.created_at)}</dd>
        {doc.failure_reason !== null && (
          <>
            <dt className="text-muted-foreground">Problem</dt>
            <dd>{doc.failure_reason}</dd>
          </>
        )}
      </dl>
      <div className="flex items-center gap-3">
        <Button
          variant="outline"
          onClick={() => openOriginal.mutate()}
          disabled={openOriginal.isPending}
        >
          View original
        </Button>
        {doc.status === "FAILED" && (
          <Button onClick={() => retry.mutate()} disabled={retry.isPending}>
            Retry
          </Button>
        )}
        {openOriginal.isError && (
          <span role="alert" className="text-sm text-destructive">
            Couldn&apos;t open the file. Try again.
          </span>
        )}
      </div>
    </div>
  );
}
