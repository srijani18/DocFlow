import { LoaderCircleIcon } from "lucide-react";

import type { components } from "@/generated/api";

type Status = components["schemas"]["DocumentStatus"];

const LABEL: Record<Status, string> = {
  UPLOADED: "Queued",
  CLASSIFYING: "Classifying",
  EXTRACTING: "Extracting",
  NEEDS_REVIEW: "Needs review",
  FAILED: "Failed",
};

const TONE: Record<Status, string> = {
  UPLOADED: "bg-muted text-muted-foreground",
  CLASSIFYING: "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300",
  EXTRACTING: "bg-violet-50 text-violet-700 dark:bg-violet-950 dark:text-violet-300",
  NEEDS_REVIEW: "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  FAILED: "bg-red-50 text-red-700 dark:bg-red-950 dark:text-red-300",
};

const IN_PROGRESS = new Set<Status>(["UPLOADED", "CLASSIFYING", "EXTRACTING"]);

export function DocumentStatusBadge({ status }: { status: Status }) {
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-medium whitespace-nowrap ${TONE[status]}`}
    >
      {IN_PROGRESS.has(status) && <LoaderCircleIcon className="size-3 animate-spin" aria-hidden />}
      {LABEL[status]}
    </span>
  );
}
