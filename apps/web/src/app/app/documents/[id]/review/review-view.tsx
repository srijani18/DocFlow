"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useMemo, useState } from "react";

import { DocumentStatusBadge } from "@/components/document-status";
import { MeGate } from "@/components/me-gate";
import { Panel } from "@/components/page-header";
import { DocumentViewer } from "@/components/review/document-viewer";
import { ProblemList, type ReviewProblem } from "@/components/review/problem-list";
import { SchemaForm } from "@/components/review/schema-form";
import { Button } from "@/components/ui/button";
import {
  documentKeys,
  type DocumentSummary,
  type Extraction,
  fetchDocument,
  fetchExtraction,
  fetchIssues,
  type ValidationIssue,
} from "@/lib/api/documents";
import { currentWorkspace } from "@/lib/api/me";
import { approveDocument, fetchSchema, saveCorrections } from "@/lib/api/review";
import { ApiError, problemMessage } from "@/lib/api/transient";
import {
  type Data,
  type Draft,
  dataFrom,
  draftErrors,
  draftFrom,
  type FormSpec,
  formSpec,
} from "@/lib/review/form";

/** Fields below this confidence are flagged for checking (F5 spec D2, F7 AC2). */
export const LOW_CONFIDENCE = 0.8;

export function ReviewPageView() {
  const { id } = useParams<{ id: string }>();
  return (
    <MeGate>
      {(me) => {
        const membership = currentWorkspace(me);
        if (membership === undefined) {
          return <p className="text-sm">You don&apos;t belong to a workspace yet.</p>;
        }
        return <Review workspaceId={membership.workspace.id} documentId={id} />;
      }}
    </MeGate>
  );
}

export function problemsFor(
  extraction: Extraction,
  issues: ValidationIssue[],
  spec: FormSpec,
): ReviewProblem[] {
  const order = [
    ...spec.fields.map((field) => field.path),
    ...spec.tables.map((table) => table.path),
  ];
  const rank = (path: string) => {
    const index = order.findIndex(
      (p) => path === p || path.startsWith(`${p}.`) || p.startsWith(`${path}.`),
    );
    return index === -1 ? order.length : index;
  };
  // Info notes (e.g. a first-time vendor) stay on the detail page: nothing to fix here.
  const fromIssues = issues
    .filter((issue) => !issue.fixed_by_agent && issue.severity !== "info")
    .map((issue) => ({
      id: issue.id,
      path: issue.paths[0] ?? "",
      message: issue.message,
      tone: issue.severity as "error" | "warning",
    }));
  const fromConfidence = Object.entries(extraction.confidence)
    .filter(([, score]) => score < LOW_CONFIDENCE)
    .map(([path, score]) => ({
      id: `confidence:${path}`,
      path,
      message: `${path} is only ${Math.round(score * 100)}% certain`,
      tone: "confidence" as const,
    }));
  return [...fromIssues, ...fromConfidence].sort((a, b) => rank(a.path) - rank(b.path));
}

function focusPath(path: string) {
  const inputs = [...document.querySelectorAll<HTMLElement>("[data-path]")];
  const target = inputs.find((el) => {
    const p = el.dataset.path ?? "";
    return p === path || p.startsWith(`${path}.`);
  });
  target?.focus({ preventScroll: true });
  target?.scrollIntoView?.({ block: "center", behavior: "smooth" });
}

function sameDraft(a: Draft, b: Draft) {
  return JSON.stringify(a) === JSON.stringify(b);
}

export function Review({ workspaceId, documentId }: { workspaceId: string; documentId: string }) {
  const queryClient = useQueryClient();
  const detailKey = documentKeys.detail(workspaceId, documentId);
  const document = useQuery({
    queryKey: detailKey,
    queryFn: () => fetchDocument(workspaceId, documentId),
  });
  const extraction = useQuery({
    queryKey: [...detailKey, "extraction"],
    queryFn: () => fetchExtraction(workspaceId, documentId),
  });
  const issues = useQuery({
    queryKey: [...detailKey, "issues"],
    queryFn: () => fetchIssues(workspaceId, documentId),
  });
  const schemaId = extraction.data?.schema_id;
  const schema = useQuery({
    queryKey: ["schema", schemaId],
    queryFn: () => fetchSchema(schemaId!),
    enabled: schemaId !== undefined,
    staleTime: Infinity,
  });

  if (document.isError || extraction.isError || schema.isError) {
    return (
      <div role="alert" className="flex flex-col items-start gap-2 text-sm">
        Couldn&apos;t load this document for review.
        <Link href={`/app/documents/${documentId}`} className="underline underline-offset-4">
          Back to the document
        </Link>
      </div>
    );
  }
  if (!document.data || !extraction.data || !schema.data || !issues.data) {
    return <p className="text-sm text-muted-foreground">Loading review…</p>;
  }
  return (
    <ReviewForm
      // A new version (saved here or elsewhere) starts a fresh form.
      key={extraction.data.version}
      workspaceId={workspaceId}
      documentId={documentId}
      doc={document.data}
      extraction={extraction.data}
      issues={issues.data}
      spec={formSpec(schema.data)}
      onSaved={(saved) => {
        queryClient.setQueryData([...detailKey, "extraction"], saved);
        void queryClient.invalidateQueries({ queryKey: detailKey });
      }}
      onReload={() => void queryClient.invalidateQueries({ queryKey: detailKey })}
    />
  );
}

function ReviewForm({
  workspaceId,
  documentId,
  doc,
  extraction,
  issues,
  spec,
  onSaved,
  onReload,
}: {
  workspaceId: string;
  documentId: string;
  doc: DocumentSummary;
  extraction: Extraction;
  issues: ValidationIssue[];
  spec: FormSpec;
  onSaved: (saved: Extraction) => void;
  onReload: () => void;
}) {
  const queryClient = useQueryClient();
  const initial = useMemo(() => draftFrom(spec, extraction.data as Data), [spec, extraction]);
  const [draft, setDraft] = useState<Draft>(initial);
  const [cursor, setCursor] = useState(-1);
  const [confirmErrors, setConfirmErrors] = useState<string | null>(null);
  const readOnly = doc.status !== "NEEDS_REVIEW";
  const errors = draftErrors(spec, draft);
  const valid = Object.keys(errors).length === 0;
  const dirty = !sameDraft(draft, initial);
  const problems = problemsFor(extraction, issues, spec);
  const highlighted = (path: string) =>
    problems.some(
      (problem) =>
        problem.path === path ||
        path.startsWith(`${problem.path}.`) ||
        problem.path.startsWith(`${path}.`),
    );
  const corrected = () => dataFrom(spec, draft, extraction.data as Data);

  const save = useMutation({
    mutationFn: () => saveCorrections(workspaceId, documentId, extraction.version, corrected()),
    onSuccess: onSaved,
  });
  const approve = useMutation({
    mutationFn: (acceptErrors: boolean) =>
      approveDocument(workspaceId, documentId, {
        version: extraction.version,
        data: dirty ? corrected() : null,
        accept_errors: acceptErrors,
      }),
    onSuccess: (approved) => {
      setConfirmErrors(null);
      queryClient.setQueryData(documentKeys.detail(workspaceId, documentId), approved);
      void queryClient.invalidateQueries({ queryKey: documentKeys.list(workspaceId) });
      void queryClient.invalidateQueries({
        queryKey: [...documentKeys.detail(workspaceId, documentId), "extraction"],
      });
    },
    onError: (error) => {
      if (error instanceof ApiError && error.problem?.type.endsWith("/open-errors")) {
        setConfirmErrors(error.problem.detail ?? error.problem.title);
      }
    },
  });
  const failure = [save.error, approve.error].find(
    (error) =>
      error && !(error instanceof ApiError && error.problem?.type.endsWith("/open-errors")),
  );
  const conflict = failure instanceof ApiError && failure.status === 409;

  const goTo = (index: number) => {
    const problem = problems[index];
    if (problem) {
      setCursor(index);
      focusPath(problem.path);
    }
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex min-w-0 items-center gap-3">
          <Link
            href={`/app/documents/${documentId}`}
            className="text-sm text-muted-foreground hover:underline"
          >
            ← Document
          </Link>
          <h1 className="truncate text-xl font-semibold tracking-tight">Review {doc.filename}</h1>
          <DocumentStatusBadge status={doc.status} />
        </div>
        {!readOnly && (
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              disabled={!dirty || !valid || save.isPending}
              onClick={() => save.mutate()}
            >
              {save.isPending ? "Saving…" : "Save"}
            </Button>
            <Button disabled={!valid || approve.isPending} onClick={() => approve.mutate(false)}>
              {approve.isPending ? "Approving…" : "Approve"}
            </Button>
          </div>
        )}
      </div>
      {confirmErrors !== null && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200"
        >
          <span>
            <span className="font-medium">Checks found errors: </span>
            {confirmErrors}
          </span>
          <Button variant="destructive" size="sm" onClick={() => approve.mutate(true)}>
            Approve anyway
          </Button>
        </div>
      )}
      {failure && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-3 rounded-xl bg-red-50 px-4 py-3 text-sm text-red-800 dark:bg-red-950 dark:text-red-200"
        >
          {conflict
            ? (failure as ApiError).problem?.title
            : failure instanceof ApiError && failure.status === 422
              ? "Some values aren't valid. Check the highlighted fields."
              : problemMessage(failure, "Couldn't save. Try again.")}
          {conflict && (
            <Button variant="outline" size="sm" onClick={onReload}>
              Reload document
            </Button>
          )}
        </div>
      )}
      {readOnly && doc.status === "APPROVED" && (
        <p className="rounded-xl bg-emerald-50 px-4 py-3 text-sm text-emerald-800 dark:bg-emerald-950 dark:text-emerald-200">
          Approved. Approved documents are read-only.
        </p>
      )}
      {/* minmax(0, 1fr): a wide line-items table scrolls inside its column, not the page. */}
      <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Panel className="lg:sticky lg:top-4 lg:h-[calc(100vh-6rem)]">
          <DocumentViewer
            workspaceId={workspaceId}
            documentId={documentId}
            contentType={doc.content_type}
            filename={doc.filename}
          />
        </Panel>
        <Panel className="flex flex-col gap-6">
          {!readOnly && (
            <ProblemList
              problems={problems}
              onGoTo={(problem) => goTo(problems.indexOf(problem))}
              onNext={() => goTo((cursor + 1) % problems.length)}
            />
          )}
          <SchemaForm
            spec={spec}
            draft={draft}
            errors={errors}
            isHighlighted={highlighted}
            readOnly={readOnly}
            onChange={setDraft}
          />
          <p className="text-xs text-muted-foreground">
            {extraction.schema_id} · version {extraction.version} ({extraction.source})
          </p>
        </Panel>
      </div>
    </div>
  );
}
