"use client";

import { useQuery } from "@tanstack/react-query";

import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { documentKeys, fetchExtraction } from "@/lib/api/documents";
import { layoutFields, type Scalar } from "@/lib/extraction-fields";

/** Fields below this confidence are highlighted for checking (F5 spec D2). */
export const LOW_CONFIDENCE = 0.8;

function Value({ value }: { value: Scalar }) {
  if (value === null) return <span className="text-muted-foreground">—</span>;
  return <span className="break-words">{String(value)}</span>;
}

function Confidence({ score }: { score: number | undefined }) {
  if (score === undefined) return null;
  return <span className="ml-2 text-xs text-muted-foreground">{Math.round(score * 100)}%</span>;
}

function lowClass(score: number | undefined) {
  return score !== undefined && score < LOW_CONFIDENCE ? "bg-amber-100 dark:bg-amber-950/60" : "";
}

/** The current extraction: fields, line-item tables and a raw JSON view (F5 AC6). */
export function ExtractionView({
  workspaceId,
  documentId,
}: {
  workspaceId: string;
  documentId: string;
}) {
  const extraction = useQuery({
    queryKey: [...documentKeys.detail(workspaceId, documentId), "extraction"],
    queryFn: () => fetchExtraction(workspaceId, documentId),
  });

  if (extraction.isPending) {
    return <p className="text-sm text-muted-foreground">Loading extracted data…</p>;
  }
  if (extraction.isError) {
    return <p className="text-sm text-muted-foreground">No extracted data yet.</p>;
  }
  const { data, confidence, schema_id, version } = extraction.data;
  const { fields, tables } = layoutFields(data);
  const lowCount = Object.values(confidence).filter((score) => score < LOW_CONFIDENCE).length;

  return (
    <section className="flex flex-col gap-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-lg font-semibold">Extracted data</h3>
        <p className="text-xs text-muted-foreground">
          {schema_id} · version {version}
          {lowCount > 0 && ` · ${lowCount} field${lowCount === 1 ? "" : "s"} to check`}
        </p>
      </div>
      <Tabs defaultValue="fields">
        <TabsList>
          <TabsTrigger value="fields">Fields</TabsTrigger>
          <TabsTrigger value="json">Raw JSON</TabsTrigger>
        </TabsList>
        <TabsContent value="fields" className="flex flex-col gap-6">
          <dl className="grid grid-cols-[minmax(8rem,auto)_1fr] gap-x-6 text-sm">
            {fields.map((field) => (
              <div
                key={field.path}
                data-path={field.path}
                className={`col-span-2 grid grid-cols-subgrid rounded px-1 py-1 ${lowClass(confidence[field.path])}`}
              >
                <dt className="text-muted-foreground">{field.label}</dt>
                <dd>
                  <Value value={field.value} />
                  <Confidence score={confidence[field.path]} />
                </dd>
              </div>
            ))}
          </dl>
          {tables.map((table) => (
            <div key={table.path} className="flex flex-col gap-2">
              <h4 className="text-sm font-medium">{table.label}</h4>
              {table.rows.length === 0 ? (
                <p className="text-sm text-muted-foreground">None</p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-sm">
                    <thead className="text-muted-foreground">
                      <tr>
                        {table.columns.map((column) => (
                          <th key={column.key} className="py-1 pr-4 font-normal">
                            {column.label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {table.rows.map((row) => (
                        <tr key={row.path} className="border-t">
                          {table.columns.map((column) => {
                            const path = `${row.path}.${column.key}`;
                            return (
                              <td
                                key={column.key}
                                data-path={path}
                                className={`py-1 pr-4 ${lowClass(confidence[path])}`}
                              >
                                <Value value={row.cells[column.key] ?? null} />
                                <Confidence score={confidence[path]} />
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          ))}
        </TabsContent>
        <TabsContent value="json">
          <pre className="max-h-[32rem] overflow-auto rounded-md border bg-muted p-3 text-xs">
            {JSON.stringify({ data, confidence }, null, 2)}
          </pre>
        </TabsContent>
      </Tabs>
    </section>
  );
}
