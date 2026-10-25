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

const IN_PROGRESS = new Set<Status>(["UPLOADED", "CLASSIFYING", "EXTRACTING"]);

export function DocumentStatusBadge({ status }: { status: Status }) {
  const tone =
    status === "FAILED"
      ? "border-destructive/40 text-destructive"
      : status === "NEEDS_REVIEW"
        ? "border-amber-500/40 text-amber-700 dark:text-amber-400"
        : "text-muted-foreground";
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-xs font-medium ${tone}`}
    >
      {IN_PROGRESS.has(status) && <LoaderCircleIcon className="size-3 animate-spin" aria-hidden />}
      {LABEL[status]}
    </span>
  );
}
