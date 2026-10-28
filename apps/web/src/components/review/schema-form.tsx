"use client";

import { PlusIcon, Trash2Icon } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type Draft, emptyRow, type FormSpec, type Leaf } from "@/lib/review/form";

export function fieldId(path: string): string {
  return `field-${path}`;
}

function FieldInput({
  path,
  label,
  leaf,
  value,
  error,
  highlighted,
  readOnly,
  onChange,
  compact = false,
}: {
  path: string;
  label: string;
  leaf: Leaf;
  value: string;
  error: string | undefined;
  highlighted: boolean;
  readOnly: boolean;
  onChange: (value: string) => void;
  compact?: boolean;
}) {
  const shared = {
    id: fieldId(path),
    "data-path": path,
    "aria-label": label,
    "aria-invalid": error !== undefined,
    "aria-describedby": error ? `${fieldId(path)}-error` : undefined,
    disabled: readOnly,
  };
  const tone = highlighted ? "border-amber-400 bg-amber-50/60 dark:bg-amber-950/40" : "";
  return (
    <div className={compact ? "min-w-28" : "flex flex-col gap-1"}>
      {leaf.kind === "choice" ? (
        <select
          {...shared}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          className={`h-10 w-full rounded-xl border border-input bg-transparent px-2 text-sm ${tone}`}
        >
          <option value="">—</option>
          {leaf.options?.map((option) => (
            <option key={option} value={option}>
              {option}
            </option>
          ))}
        </select>
      ) : (
        <Input
          {...shared}
          value={value}
          inputMode={leaf.kind === "number" ? "decimal" : undefined}
          placeholder={leaf.kind === "date" ? "YYYY-MM-DD" : undefined}
          onChange={(event) => onChange(event.target.value)}
          className={tone}
        />
      )}
      {error && (
        <p id={`${fieldId(path)}-error`} className="text-xs text-destructive">
          {error}
        </p>
      )}
    </div>
  );
}

/** Every field of the document type as an input, and line items and taxes as editable
 * tables (F7 AC1, AC3). */
export function SchemaForm({
  spec,
  draft,
  errors,
  isHighlighted,
  readOnly,
  onChange,
}: {
  spec: FormSpec;
  draft: Draft;
  errors: Record<string, string>;
  isHighlighted: (path: string) => boolean;
  readOnly: boolean;
  onChange: (draft: Draft) => void;
}) {
  const setField = (path: string, value: string) =>
    onChange({ ...draft, fields: { ...draft.fields, [path]: value } });
  const setRows = (table: string, rows: Record<string, string>[]) =>
    onChange({ ...draft, tables: { ...draft.tables, [table]: rows } });

  return (
    <div className="flex flex-col gap-6">
      <div className="grid gap-x-4 gap-y-3 sm:grid-cols-2">
        {spec.fields.map((field) => (
          <label key={field.path} className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">{field.label}</span>
            <FieldInput
              path={field.path}
              label={field.label}
              leaf={field.leaf}
              value={draft.fields[field.path] ?? ""}
              error={errors[field.path]}
              highlighted={isHighlighted(field.path)}
              readOnly={readOnly}
              onChange={(value) => setField(field.path, value)}
            />
          </label>
        ))}
      </div>
      {spec.tables.map((table) => {
        const rows = draft.tables[table.path] ?? [];
        return (
          <section key={table.path} className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <h4 className="text-sm font-medium">{table.label}</h4>
              {!readOnly && (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setRows(table.path, [...rows, emptyRow(table)])}
                >
                  <PlusIcon aria-hidden />
                  Add row
                </Button>
              )}
            </div>
            {rows.length === 0 ? (
              <p className="text-sm text-muted-foreground">None</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm">
                  <thead className="text-muted-foreground">
                    <tr>
                      {table.columns.map((column) => (
                        <th key={column.key} className="py-1 pr-2 font-normal whitespace-nowrap">
                          {column.label}
                        </th>
                      ))}
                      {!readOnly && <th className="sr-only">Remove</th>}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row, index) => (
                      // Rows have no identity of their own; position is what the server diffs by.
                      <tr key={index} className="align-top">
                        {table.columns.map((column) => {
                          const path = `${table.path}.${index}.${column.key}`;
                          return (
                            <td key={column.key} className="py-1 pr-2">
                              <FieldInput
                                compact
                                path={path}
                                label={`${table.label} row ${index + 1}: ${column.label}`}
                                leaf={column.leaf}
                                value={row[column.key] ?? ""}
                                error={errors[path]}
                                highlighted={isHighlighted(path)}
                                readOnly={readOnly}
                                onChange={(value) =>
                                  setRows(
                                    table.path,
                                    rows.map((r, i) =>
                                      i === index ? { ...r, [column.key]: value } : r,
                                    ),
                                  )
                                }
                              />
                            </td>
                          );
                        })}
                        {!readOnly && (
                          <td className="py-1">
                            <Button
                              variant="ghost"
                              size="icon-sm"
                              aria-label={`Remove ${table.label.toLowerCase()} row ${index + 1}`}
                              onClick={() =>
                                setRows(
                                  table.path,
                                  rows.filter((_, i) => i !== index),
                                )
                              }
                            >
                              <Trash2Icon aria-hidden />
                            </Button>
                          </td>
                        )}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
