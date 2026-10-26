"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";

import { DocTypeLabel, OTHER_NOTE } from "@/components/doc-type";
import { DocumentStatusBadge } from "@/components/document-status";
import { ExtractionView } from "./extraction-view";
import { IssuesView } from "./issues-view";
import { MeGate } from "@/components/me-gate";
import { Panel } from "@/components/page-header";
import { Button, buttonVariants } from "@/components/ui/button";
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
      <Panel>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="flex min-w-0 flex-wrap items-center gap-3">
            <h1 className="text-2xl font-semibold tracking-tight break-all">{doc.filename}</h1>
            <DocumentStatusBadge status={doc.status} />
          </div>
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
            {(doc.status === "NEEDS_REVIEW" || doc.status === "APPROVED") &&
              doc.doc_type !== null &&
              doc.doc_type !== "other" && (
                <Link
                  href={`/app/documents/${doc.id}/review`}
                  className={buttonVariants({
                    variant: doc.status === "NEEDS_REVIEW" ? "default" : "outline",
                  })}
                >
                  {doc.status === "NEEDS_REVIEW" ? "Review" : "Open review"}
                </Link>
              )}
          </div>
        </div>
        {openOriginal.isError && (
          <p role="alert" className="mt-3 text-sm text-destructive">
            Couldn&apos;t open the file. Try again.
          </p>
        )}
        {doc.doc_type === "other" && (
          <p className="mt-4 rounded-xl bg-muted px-4 py-3 text-sm">{OTHER_NOTE}.</p>
        )}
        {doc.approved_at !== null && (
          <p className="mt-4 rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
            {doc.approved_by_agent
              ? "Approved automatically: every check passed with high confidence"
              : "Approved"}{" "}
            on {formatDateTime(doc.approved_at)}.
          </p>
        )}
        {doc.failure_reason !== null && (
          <p className="mt-4 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200">
            <span className="font-medium">Problem: </span>
            {doc.failure_reason}
            {(doc.failure_code === "no_ai_key" || doc.failure_code === "key_rejected") && (
              <>
                {" "}
                <Link href="/app/settings" className="font-medium underline underline-offset-4">
                  Connect a key in Settings
                </Link>
                . The document is retried automatically once one is connected.
              </>
            )}
          </p>
        )}
        <dl className="mt-6 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-muted-foreground">Document type</dt>
            <dd className="mt-1 font-medium">
              <DocTypeLabel docType={doc.doc_type} confidence={doc.doc_type_confidence} />
            </dd>
          </div>
          <div>
            <dt className="text-muted-foreground">File type</dt>
            <dd className="mt-1 font-medium">{doc.content_type}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Size</dt>
            <dd className="mt-1 font-medium">{formatBytes(doc.size_bytes)}</dd>
          </div>
          <div>
            <dt className="text-muted-foreground">Uploaded</dt>
            <dd className="mt-1 font-medium">{formatDateTime(doc.created_at)}</dd>
          </div>
        </dl>
      </Panel>
      {(doc.status === "NEEDS_REVIEW" || doc.status === "APPROVED") &&
        doc.doc_type !== null &&
        doc.doc_type !== "other" && (
          <>
            <Panel>
              <IssuesView workspaceId={workspaceId} documentId={documentId} />
            </Panel>
            <Panel>
              <ExtractionView workspaceId={workspaceId} documentId={documentId} />
            </Panel>
          </>
        )}
    </div>
  );
}
