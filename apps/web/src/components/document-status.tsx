import type { components } from "@/generated/api";

type Status = components["schemas"]["DocumentStatus"];

const LABEL: Record<Status, string> = {
  UPLOADED: "Uploaded",
};

export function DocumentStatusBadge({ status }: { status: Status }) {
  return (
    <span className="inline-flex items-center rounded-md border px-1.5 py-0.5 text-xs font-medium">
      {LABEL[status]}
    </span>
  );
}
