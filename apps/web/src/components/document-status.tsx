import { LoaderCircleIcon } from "lucide-react";

import type { components } from "@/generated/api";

type Status = components["schemas"]["DocumentStatus"];

export const STATUS_LABEL: Record<Status, string> = {
  UPLOADED: "Queued",
  CLASSIFYING: "Classifying",
  EXTRACTING: "Extracting",
  VALIDATING: "Validating",
  NEEDS_REVIEW: "Needs review",
  APPROVED: "Approved",
  FAILED: "Failed",
};

const TONE: Record<Status, string> = {
  UPLOADED: "bg-muted text-muted-foreground",
  CLASSIFYING: "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300",
  EXTRACTING: "bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
  VALIDATING: "bg-fuchsia-50 text-fuchsia-700 dark:bg-fuchsia-950 dark:text-fuchsia-300",
  NEEDS_REVIEW: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  APPROVED: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  FAILED: "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
};

const IN_PROGRESS = new Set<Status>(["UPLOADED", "CLASSIFYING", "EXTRACTING", "VALIDATING"]);

export function DocumentStatusBadge({ status }: { status: Status }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${TONE[status]}`}
    >
      {IN_PROGRESS.has(status) && <LoaderCircleIcon className="size-3 animate-spin" aria-hidden />}
      {STATUS_LABEL[status]}
    </span>
  );
}
