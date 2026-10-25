"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import Link from "next/link";

import { DocTypeLabel } from "@/components/doc-type";
import { DocumentStatusBadge } from "@/components/document-status";
import { MeGate } from "@/components/me-gate";
import { Panel } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { UploadDropzone } from "@/components/upload-dropzone";
import { useDocumentEvents } from "@/hooks/use-document-events";
import { documentKeys, fetchDocumentPage } from "@/lib/api/documents";
import { currentWorkspace } from "@/lib/api/me";
import { formatDateTime, formatMoney } from "@/lib/format";

export function DocumentsView() {
  return (
    <MeGate>
      {(me) => {
        const membership = currentWorkspace(me);
        if (membership === undefined) {
          return <p className="text-sm">You don&apos;t belong to a workspace yet.</p>;
        }
        return (
          <div className="flex flex-col gap-6">
            <Panel>
              <UploadDropzone workspaceId={membership.workspace.id} />
            </Panel>
            <Panel>
              <DocumentList workspaceId={membership.workspace.id} />
            </Panel>
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
      <div className="overflow-x-auto">
        <table className="w-full text-left text-sm">
          <thead className="text-xs tracking-wide text-muted-foreground uppercase">
            <tr>
              <th className="py-3 pr-4 font-medium">Name</th>
              <th className="py-3 pr-4 font-medium">Status</th>
              <th className="py-3 pr-4 font-medium">Type</th>
              <th className="py-3 pr-4 font-medium">Vendor</th>
              <th className="py-3 text-right font-medium">Total</th>
              <th className="py-3 pl-6 font-medium">Uploaded</th>
            </tr>
          </thead>
          <tbody>
            {items.map((document) => (
              <tr key={document.id} className="border-t transition-colors hover:bg-muted/50">
                <td className="max-w-64 truncate py-3 pr-4">
                  <Link
                    href={`/app/documents/${document.id}`}
                    className="font-medium underline-offset-4 hover:underline"
                  >
                    {document.filename}
                  </Link>
                </td>
                <td className="py-3 pr-4">
                  <DocumentStatusBadge status={document.status} />
                </td>
                <td className="py-3 pr-4">
                  <DocTypeLabel
                    docType={document.doc_type}
                    confidence={document.doc_type_confidence}
                  />
                </td>
                <td className="max-w-48 truncate py-3 pr-4">{document.vendor_name ?? "—"}</td>
                <td className="py-3 text-right tabular-nums">
                  {formatMoney(document.total_amount, document.currency)}
                </td>
                <td className="py-3 pl-6 whitespace-nowrap text-muted-foreground">
                  {formatDateTime(document.created_at)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
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
