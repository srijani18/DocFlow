import Link from "next/link";

import { DocTypeLabel } from "@/components/doc-type";
import { DocumentStatusBadge } from "@/components/document-status";
import type { DocumentSummary } from "@/lib/api/documents";
import { snippetParts } from "@/lib/api/search";
import { formatDateTime, formatMoney } from "@/lib/format";

export type TableRow = {
  document: DocumentSummary;
  matched?: "keyword" | "meaning" | "both" | null;
  snippet?: string | null;
};

const MATCH_LABEL = { keyword: "Keyword", meaning: "Meaning", both: "Keyword + meaning" };

function Snippet({ snippet }: { snippet: string }) {
  return (
    <p className="mt-0.5 max-w-80 truncate text-xs text-muted-foreground">
      {snippetParts(snippet).map((part, index) =>
        part.match ? (
          // Parts have no identity of their own; their order never changes.
          <mark
            key={index}
            className="rounded bg-amber-100 px-0.5 text-foreground dark:bg-amber-900"
          >
            {part.text}
          </mark>
        ) : (
          <span key={index}>{part.text}</span>
        ),
      )}
    </p>
  );
}

/** The documents table shared by the list and search results. */
export function DocumentTable({ rows }: { rows: TableRow[] }) {
  const showMatch = rows.some((row) => row.matched);
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="text-xs tracking-wide text-muted-foreground uppercase">
          <tr>
            <th className="py-3 pr-4 font-medium">Name</th>
            <th className="py-3 pr-4 font-medium">Status</th>
            <th className="py-3 pr-4 font-medium">Type</th>
            <th className="py-3 pr-4 font-medium">Vendor</th>
            <th className="py-3 text-right font-medium">Total</th>
            {showMatch ? (
              <th className="py-3 pl-6 font-medium">Match</th>
            ) : (
              <th className="py-3 pl-6 font-medium">Uploaded</th>
            )}
          </tr>
        </thead>
        <tbody>
          {rows.map(({ document, matched, snippet }) => (
            <tr key={document.id} className="border-t transition-colors hover:bg-muted/50">
              <td className="max-w-64 py-3 pr-4">
                <Link
                  href={`/app/documents/${document.id}`}
                  className="block truncate font-medium underline-offset-4 hover:underline"
                >
                  {document.filename}
                </Link>
                {snippet && <Snippet snippet={snippet} />}
              </td>
              <td className="py-3 pr-4">
                <DocumentStatusBadge status={document.status} />
              </td>
              <td className="py-3 pr-4">
                <DocTypeLabel
                  docType={document.doc_type}
                  confidence={document.doc_type_confidence}
                />
              </td>
              <td className="max-w-48 truncate py-3 pr-4">{document.vendor_name ?? "—"}</td>
              <td className="py-3 text-right tabular-nums">
                {formatMoney(document.total_amount, document.currency)}
              </td>
              {showMatch ? (
                <td className="py-3 pl-6 whitespace-nowrap">
                  {matched && (
                    <span className="rounded-full bg-accent px-2.5 py-0.5 text-xs font-medium text-accent-foreground">
                      {MATCH_LABEL[matched]}
                    </span>
                  )}
                </td>
              ) : (
                <td className="py-3 pl-6 whitespace-nowrap text-muted-foreground">
                  {formatDateTime(document.created_at)}
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
