"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";

import { DocTypeLabel } from "@/components/doc-type";
import { DocumentStatusBadge } from "@/components/document-status";
import { MeGate } from "@/components/me-gate";
import { Button } from "@/components/ui/button";
import { UploadDropzone } from "@/components/upload-dropzone";
import { useDocumentEvents } from "@/hooks/use-document-events";
import { documentKeys, fetchDocumentPage } from "@/lib/api/documents";
import { currentWorkspace } from "@/lib/api/me";
import { formatBytes, formatDateTime } from "@/lib/format";

export function DocumentsView() {
  return (
    <MeGate>
      {(me) => {
        const membership = currentWorkspace(me);
        if (membership === undefined) {
          return <p className="text-sm">You don&apos;t belong to a workspace yet.</p>;
        }
        return (
          <div className="flex flex-col gap-8">
            <UploadDropzone workspaceId={membership.workspace.id} />
            <DocumentList workspaceId={membership.workspace.id} />
          </div>
        );
      }}
    </MeGate>
  );
}

/** The workspace's documents, newest first, 50 at a time (F2 AC8). */
export function DocumentList({ workspaceId }: { workspaceId: string }) {
  useDocumentEvents(workspaceId);
  const documents = useInfiniteQuery({
    queryKey: documentKeys.list(workspaceId),
    queryFn: ({ pageParam }) => fetchDocumentPage(workspaceId, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor,
  });

  if (documents.isPending) {
    return <p className="text-sm text-muted-foreground">Loading documents…</p>;
  }
  if (documents.isError) {
    return (
      <div role="alert" className="flex items-center gap-3 text-sm">
        Couldn&apos;t load documents.
        <Button variant="outline" size="sm" onClick={() => void documents.refetch()}>
          Try again
        </Button>
      </div>
    );
  }
  const items = documents.data.pages.flatMap((page) => page.items);
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No documents yet.</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      <table className="w-full text-left text-sm">
        <thead className="text-muted-foreground">
          <tr>
            <th className="py-2 font-normal">Name</th>
            <th className="py-2 font-normal">Status</th>
            <th className="py-2 font-normal">Type</th>
            <th className="py-2 font-normal">Size</th>
            <th className="py-2 font-normal">Uploaded</th>
          </tr>
        </thead>
        <tbody>
          {items.map((document) => (
            <tr key={document.id} className="border-t">
              <td className="max-w-64 truncate py-2">
                <Link
                  href={`/app/documents/${document.id}`}
                  className="underline-offset-4 hover:underline"
                >
                  {document.filename}
                </Link>
              </td>
              <td className="py-2">
                <DocumentStatusBadge status={document.status} />
              </td>
              <td className="py-2">
                <DocTypeLabel
                  docType={document.doc_type}
                  confidence={document.doc_type_confidence}
                />
              </td>
              <td className="py-2">{formatBytes(document.size_bytes)}</td>
              <td className="py-2">{formatDateTime(document.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
      {documents.hasNextPage && (
        <Button
          variant="outline"
          size="sm"
          className="self-start"
          disabled={documents.isFetchingNextPage}
          onClick={() => void documents.fetchNextPage()}
        >
          Load more
        </Button>
      )}
    </div>
  );
}
