"use client";

import { useQueryClient } from "@tanstack/react-query";
import { UploadIcon } from "lucide-react";
import Link from "next/link";
import { useRef, useState, type DragEvent } from "react";

import { Button } from "@/components/ui/button";
import { ApiError, isTransient } from "@/lib/api/transient";
import { ACCEPT, uploadFile, validateFile, type UploadPhase } from "@/lib/upload";

type RowState = UploadPhase | "rejected" | "done" | "duplicate" | "failed";
type Row = { key: string; name: string; state: RowState; message?: string; documentId?: string };

const STATE_LABEL: Record<UploadPhase | "done", string> = {
  hashing: "Checking…",
  uploading: "Uploading…",
  finishing: "Saving…",
  done: "Uploaded",
};

function describeError(error: unknown): string {
  if (isTransient(error)) {
    return "Couldn't reach the server. Try again in a moment.";
  }
  if (error instanceof ApiError) {
    return error.problem?.detail ?? error.problem?.title ?? "The server rejected this file.";
  }
  return error instanceof Error ? error.message : "Upload failed.";
}

/** Drag-and-drop upload of several files at once, each with its own progress (F2 AC6). */
export function UploadDropzone({ workspaceId }: { workspaceId: string }) {
  const queryClient = useQueryClient();
  const inputRef = useRef<HTMLInputElement>(null);
  const [rows, setRows] = useState<Row[]>([]);
  const [dragging, setDragging] = useState(false);

  function update(key: string, patch: Partial<Row>) {
    setRows((current) => current.map((row) => (row.key === key ? { ...row, ...patch } : row)));
  }

  function addFiles(files: Iterable<File>) {
    for (const file of files) {
      const key = crypto.randomUUID();
      const problem = validateFile(file);
      if (problem !== null) {
        setRows((current) => [
          ...current,
          { key, name: file.name, state: "rejected", message: problem },
        ]);
        continue;
      }
      setRows((current) => [...current, { key, name: file.name, state: "hashing" }]);
      // Each file runs on its own, so one failure never stops the others (AC6).
      uploadFile(workspaceId, file, (phase) => update(key, { state: phase }))
        .then((outcome) => {
          update(key, {
            state: outcome.kind === "created" ? "done" : "duplicate",
            documentId: outcome.document.id,
          });
          void queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
        })
        .catch((error: unknown) => update(key, { state: "failed", message: describeError(error) }));
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault();
    setDragging(false);
    addFiles(Array.from(event.dataTransfer.files));
  }

  return (
    <section className="flex flex-col gap-3">
      <div
        data-testid="dropzone"
        onDragOver={(event) => {
          event.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`flex flex-col items-center gap-3 rounded-2xl border-2 border-dashed p-10 text-center text-sm transition-colors ${
          dragging ? "border-primary bg-accent" : "border-primary/25 bg-surface"
        }`}
      >
        <span className="bg-brand-gradient inline-flex size-12 items-center justify-center rounded-2xl text-white shadow-md shadow-primary/25">
          <UploadIcon className="size-5" aria-hidden />
        </span>
        <p className="text-base font-medium">Drop PDFs, PNGs or JPEGs here</p>
        <p className="-mt-2 text-muted-foreground">Up to 10 MB each, several at once</p>
        <Button onClick={() => inputRef.current?.click()}>Choose files</Button>
        <input
          ref={inputRef}
          type="file"
          multiple
          accept={ACCEPT}
          aria-label="Choose files"
          className="hidden"
          onChange={(event) => {
            addFiles(Array.from(event.target.files ?? []));
            event.target.value = "";
          }}
        />
        <p className="text-xs text-muted-foreground">
          Upload only sample or synthetic documents. Files are processed by free AI services that
          may keep what they receive.
        </p>
      </div>
      {rows.length > 0 && (
        <ul className="flex flex-col gap-1 text-sm" aria-label="Uploads">
          {rows.map((row) => (
            <li key={row.key} className="flex items-center justify-between gap-4">
              <span className="truncate">{row.name}</span>
              <UploadRowStatus row={row} />
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

function UploadRowStatus({ row }: { row: Row }) {
  if (row.state === "rejected" || row.state === "failed") {
    return <span className="text-destructive">{row.message}</span>;
  }
  if (row.state === "duplicate") {
    return (
      <span className="text-muted-foreground">
        Already uploaded ·{" "}
        <Link href={`/app/documents/${row.documentId}`} className="underline underline-offset-4">
          View
        </Link>
      </span>
    );
  }
  return <span className="text-muted-foreground">{STATE_LABEL[row.state]}</span>;
}
