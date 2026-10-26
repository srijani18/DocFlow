"use client";

import { useInfiniteQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { MeGate } from "@/components/me-gate";
import { Panel } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { UploadDropzone } from "@/components/upload-dropzone";
import { useDocumentEvents } from "@/hooks/use-document-events";
import { documentKeys, fetchDocumentPage } from "@/lib/api/documents";
import { currentWorkspace } from "@/lib/api/me";
import {
  activeParams,
  EMPTY_SEARCH,
  isSearching,
  type SearchParams,
  searchDocuments,
} from "@/lib/api/search";

import { DocumentTable } from "./document-table";
import { SearchBar } from "./search-bar";

const SEARCH_DELAY_MS = 300;

function useDebounced<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}

export function DocumentsView() {
  return (
    <MeGate>
      {(me) => {
        const membership = currentWorkspace(me);
        if (membership === undefined) {
          return <p className="text-sm">You don&apos;t belong to a workspace yet.</p>;
        }
        return <Documents workspaceId={membership.workspace.id} />;
      }}
    </MeGate>
  );
}

export function Documents({ workspaceId }: { workspaceId: string }) {
  const [search, setSearch] = useState<SearchParams>(EMPTY_SEARCH);
  const applied = useDebounced(search, SEARCH_DELAY_MS);
  return (
    <div className="flex flex-col gap-6">
      <Panel>
        <UploadDropzone workspaceId={workspaceId} />
      </Panel>
      <Panel className="flex flex-col gap-5">
        <SearchBar value={search} onChange={setSearch} />
        {isSearching(applied) ? (
          <SearchResultsList workspaceId={workspaceId} params={applied} />
        ) : (
          <DocumentList workspaceId={workspaceId} />
        )}
      </Panel>
    </div>
  );
}

function LoadError({ onRetry }: { onRetry: () => void }) {
  return (
    <div role="alert" className="flex items-center gap-3 text-sm">
      Couldn&apos;t load documents.
      <Button variant="outline" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}

function LoadMore({
  visible,
  busy,
  onClick,
}: {
  visible: boolean;
  busy: boolean;
  onClick: () => void;
}) {
  if (!visible) return null;
  return (
    <Button variant="outline" size="sm" className="self-start" disabled={busy} onClick={onClick}>
      Load more
    </Button>
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
    return <LoadError onRetry={() => void documents.refetch()} />;
  }
  const items = documents.data.pages.flatMap((page) => page.items);
  if (items.length === 0) {
    return <p className="text-sm text-muted-foreground">No documents yet.</p>;
  }
  return (
    <div className="flex flex-col gap-3">
      <DocumentTable rows={items.map((document) => ({ document }))} />
      <LoadMore
        visible={documents.hasNextPage}
        busy={documents.isFetchingNextPage}
        onClick={() => void documents.fetchNextPage()}
      />
    </div>
  );
}

/** Search results: best match first, with why each matched (F8 AC1). */
export function SearchResultsList({
  workspaceId,
  params,
}: {
  workspaceId: string;
  params: SearchParams;
}) {
  // Live status updates invalidate everything under the list key, results included.
  useDocumentEvents(workspaceId);
  const results = useInfiniteQuery({
    queryKey: [...documentKeys.list(workspaceId), "search", activeParams(params)],
    queryFn: ({ pageParam }) => searchDocuments(workspaceId, params, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor,
  });

  if (results.isPending) {
    return <p className="text-sm text-muted-foreground">Searching…</p>;
  }
  if (results.isError) {
    return <LoadError onRetry={() => void results.refetch()} />;
  }
  const hits = results.data.pages.flatMap((page) => page.items);
  const keywordOnly = results.data.pages.some((page) => !page.semantic);
  return (
    <div className="flex flex-col gap-3">
      {keywordOnly && (
        <p className="rounded-xl bg-muted px-4 py-2 text-sm text-muted-foreground">
          Showing keyword matches only. Matching by meaning needs a working Gemini key in Settings.
        </p>
      )}
      {hits.length === 0 ? (
        <p className="text-sm text-muted-foreground">No documents match.</p>
      ) : (
        <DocumentTable rows={hits} />
      )}
      <LoadMore
        visible={results.hasNextPage}
        busy={results.isFetchingNextPage}
        onClick={() => void results.fetchNextPage()}
      />
    </div>
  );
}
