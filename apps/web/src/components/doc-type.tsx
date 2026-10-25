import type { components } from "@/generated/api";

type DocType = components["schemas"]["DocType"];

const LABEL: Record<DocType, string> = {
  invoice: "Invoice",
  receipt: "Receipt",
  purchase_order: "Purchase order",
  other: "Other",
};

/** The classified type and how sure the model was (F4 AC1); a dash until classified. */
export function DocTypeLabel({
  docType,
  confidence,
}: {
  docType: DocType | null;
  confidence: number | null;
}) {
  if (docType === null) {
    return <span className="text-muted-foreground">—</span>;
  }
  return (
    <span>
      {LABEL[docType]}
      {confidence !== null && (
        <span className="text-muted-foreground"> · {Math.round(confidence * 100)}%</span>
      )}
    </span>
  );
}

export const OTHER_NOTE = "Not an invoice, receipt or purchase order";
