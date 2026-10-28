"use client";

import { useQuery } from "@tanstack/react-query";

import { Button } from "@/components/ui/button";
import { fetchFileUrl } from "@/lib/api/documents";

/** The original file: the browser's own PDF viewer, or the image (F7 D1). Links last
 * 5 minutes, so Reload fetches a fresh one. */
export function DocumentViewer({
  workspaceId,
  documentId,
  contentType,
  filename,
}: {
  workspaceId: string;
  documentId: string;
  contentType: string;
  filename: string;
}) {
  const url = useQuery({
    queryKey: ["file-url", workspaceId, documentId],
    queryFn: () => fetchFileUrl(workspaceId, documentId),
    staleTime: 4 * 60 * 1000,
    refetchOnWindowFocus: false,
  });

  return (
    <div className="flex h-full flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="truncate text-sm font-medium">{filename}</h2>
        <Button variant="outline" size="sm" onClick={() => void url.refetch()}>
          Reload
        </Button>
      </div>
      {url.isPending ? (
        <p className="text-sm text-muted-foreground">Loading the original…</p>
      ) : url.isError ? (
        <p role="alert" className="text-sm text-destructive">
          Couldn&apos;t load the original. Try Reload.
        </p>
      ) : contentType === "application/pdf" ? (
        <iframe
          title={`Original: ${filename}`}
          src={url.data}
          className="min-h-[60vh] w-full flex-1 rounded-xl border bg-muted"
        />
      ) : (
        <div className="min-h-[60vh] flex-1 overflow-auto rounded-xl border bg-muted">
          {/* eslint-disable-next-line @next/next/no-img-element -- a short-lived signed URL */}
          <img src={url.data} alt={`Original: ${filename}`} className="w-full" />
        </div>
      )}
    </div>
  );
}
