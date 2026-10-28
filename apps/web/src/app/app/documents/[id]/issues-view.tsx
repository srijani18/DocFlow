"use client";

import { useQuery } from "@tanstack/react-query";
import { CheckIcon } from "lucide-react";

import { documentKeys, fetchIssues, type ValidationIssue } from "@/lib/api/documents";

const SEVERITY_ORDER = { error: 0, warning: 1, info: 2 } as const;

const SEVERITY_TONE = {
  error: "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
  warning: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  info: "bg-muted text-muted-foreground",
} as const;

function IssueRow({ issue }: { issue: ValidationIssue }) {
  return (
    <li className="flex flex-col gap-1 py-3 sm:flex-row sm:items-start sm:gap-3">
      {issue.fixed_by_agent ? (
        <span className="inline-flex w-fit items-center gap-1 rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
          <CheckIcon className="size-3" aria-hidden />
          Fixed by agent
        </span>
      ) : (
        <span
          className={`w-fit rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${SEVERITY_TONE[issue.severity]}`}
        >
          {issue.severity}
        </span>
      )}
      <div className="min-w-0 text-sm">
        <p className={issue.fixed_by_agent ? "text-muted-foreground" : ""}>{issue.message}</p>
        <p className="mt-0.5 font-mono text-xs break-all text-muted-foreground">
          {issue.paths.join(", ")}
        </p>
      </div>
    </li>
  );
}

/** What the validation agent found: open problems first, then what it fixed (F6 AC2). */
export function IssuesView({
  workspaceId,
  documentId,
}: {
  workspaceId: string;
  documentId: string;
}) {
  const issues = useQuery({
    queryKey: [...documentKeys.detail(workspaceId, documentId), "issues"],
    queryFn: () => fetchIssues(workspaceId, documentId),
  });

  if (issues.isPending) {
    return <p className="text-sm text-muted-foreground">Loading checks…</p>;
  }
  if (issues.isError) {
    return <p className="text-sm text-muted-foreground">Checks aren&apos;t available yet.</p>;
  }
  const sorted = [...issues.data].sort(
    (a, b) =>
      Number(a.fixed_by_agent) - Number(b.fixed_by_agent) ||
      SEVERITY_ORDER[a.severity] - SEVERITY_ORDER[b.severity],
  );
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-lg font-semibold">Checks</h3>
      {sorted.length === 0 ? (
        <p className="text-sm text-muted-foreground">Every check passed.</p>
      ) : (
        <ul className="divide-y">
          {sorted.map((issue) => (
            <IssueRow key={issue.id} issue={issue} />
          ))}
        </ul>
      )}
    </section>
  );
}
