"use client";

import { useMutation } from "@tanstack/react-query";
import { DownloadIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { type ExportFormat, exportDocuments, saveFile } from "@/lib/api/export";
import { isSearching, type SearchParams } from "@/lib/api/search";
import { ApiError, problemMessage } from "@/lib/api/transient";

/** Export what the search shows (F9): approved documents by default. */
export function ExportMenu({ workspaceId, search }: { workspaceId: string; search: SearchParams }) {
  const [open, setOpen] = useState(false);
  const [includeUnapproved, setIncludeUnapproved] = useState(false);
  const download = useMutation({
    mutationFn: (format: ExportFormat) =>
      exportDocuments(workspaceId, search, { format, includeUnapproved }),
    onSuccess: ({ blob, filename }) => saveFile(blob, filename),
  });
  const problem =
    download.error instanceof ApiError && download.error.status === 422
      ? (download.error.problem?.detail ?? "Narrow the filters and try again.")
      : download.isError
        ? problemMessage(download.error, "Couldn't export. Try again.")
        : null;

  return (
    <div className="relative">
      <Button variant="outline" onClick={() => setOpen(!open)} aria-expanded={open}>
        <DownloadIcon aria-hidden />
        Export
      </Button>
      {open && (
        <div
          role="dialog"
          aria-label="Export documents"
          className="absolute right-0 z-10 mt-2 flex w-72 flex-col gap-3 rounded-2xl border bg-card p-4 text-sm shadow-lg"
        >
          <p className="text-muted-foreground">
            {isSearching(search)
              ? "The documents matching your search and filters."
              : "All documents in the workspace."}{" "}
            Approved ones only, unless you include the rest.
          </p>
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={includeUnapproved}
              onChange={(event) => setIncludeUnapproved(event.target.checked)}
            />
            Include documents not yet approved
          </label>
          <div className="flex gap-2">
            <Button
              className="flex-1"
              disabled={download.isPending}
              onClick={() => download.mutate("csv")}
            >
              CSV (.zip)
            </Button>
            <Button
              variant="outline"
              className="flex-1"
              disabled={download.isPending}
              onClick={() => download.mutate("json")}
            >
              JSON
            </Button>
          </div>
          {download.isPending && <p className="text-muted-foreground">Preparing the file…</p>}
          {problem && (
            <p role="alert" className="text-destructive">
              {problem}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
