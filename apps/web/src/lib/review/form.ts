/**
 * The review form's model, generated from the document's bundled JSON Schema (F7 D2), so a
 * new document type needs no new UI. Values are edited as text and turned back into data
 * on save. Paths are dotted and zero-based, like the confidence map and issues.
 */

import { humanize } from "@/lib/extraction-fields";

type Schema = Record<string, unknown>;
export type Data = Record<string, unknown>;

export type Leaf = {
  kind: "text" | "number" | "date" | "choice";
  pattern?: string;
  options?: string[];
};

export type FieldSpec = { path: string; label: string; leaf: Leaf };
export type TableSpec = {
  path: string;
  label: string;
  columns: { key: string; label: string; leaf: Leaf }[];
};
export type FormSpec = { fields: FieldSpec[]; tables: TableSpec[] };

/** Text per field path, and text rows per table. "" means null. */
export type Draft = {
  fields: Record<string, string>;
  tables: Record<string, Record<string, string>[]>;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** `anyOf: [X, {type: null}]` → X; anything else unchanged. */
function unwrap(schema: Schema): Schema {
  const options = schema.anyOf;
  if (Array.isArray(options)) {
    const real = options.filter((option) => isRecord(option) && option.type !== "null");
    if (real.length === 1) return real[0] as Schema;
  }
  return schema;
}

function types(schema: Schema): string[] {
  const type = schema.type;
  return Array.isArray(type) ? (type as string[]) : typeof type === "string" ? [type] : [];
}

function leafOf(schema: Schema): Leaf {
  const node = unwrap(schema);
  if (Array.isArray(node.enum)) return { kind: "choice", options: node.enum as string[] };
  if (types(node).some((t) => t === "number" || t === "integer")) return { kind: "number" };
  if (node.format === "date") return { kind: "date" };
  return typeof node.pattern === "string"
    ? { kind: "text", pattern: node.pattern }
    : { kind: "text" };
}

function properties(schema: Schema): [string, Schema][] {
  const props = unwrap(schema).properties;
  return isRecord(props) ? (Object.entries(props) as [string, Schema][]) : [];
}

function label(path: string): string {
  return path.split(".").map(humanize).join(" › ");
}

function leaves(schema: Schema, prefix: string): { key: string; leaf: Leaf }[] {
  const children = properties(schema);
  if (children.length === 0) return [{ key: prefix, leaf: leafOf(schema) }];
  return children.flatMap(([key, child]) => leaves(child, prefix ? `${prefix}.${key}` : key));
}

function itemsOf(schema: Schema): Schema | null {
  const node = unwrap(schema);
  return types(node).includes("array") && isRecord(node.items) ? (node.items as Schema) : null;
}

export function formSpec(schema: Schema): FormSpec {
  const fields: FieldSpec[] = [];
  const tables: TableSpec[] = [];
  for (const [key, child] of properties(schema)) {
    const items = itemsOf(child);
    if (items !== null) {
      tables.push({
        path: key,
        label: humanize(key),
        columns: leaves(items, "").map(({ key: column, leaf }) => ({
          key: column,
          label: label(column),
          leaf,
        })),
      });
      continue;
    }
    for (const { key: path, leaf } of leaves(child, key)) {
      fields.push({ path, label: label(path), leaf });
    }
  }
  return { fields, tables };
}

export function getPath(data: unknown, path: string): unknown {
  let node = data;
  for (const part of path.split(".")) {
    if (Array.isArray(node)) node = node[Number(part)];
    else if (isRecord(node)) node = node[part];
    else return undefined;
  }
  return node;
}

function toText(value: unknown): string {
  return value === null || value === undefined ? "" : String(value);
}

export function draftFrom(spec: FormSpec, data: Data): Draft {
  return {
    fields: Object.fromEntries(spec.fields.map((f) => [f.path, toText(getPath(data, f.path))])),
    tables: Object.fromEntries(
      spec.tables.map((table) => {
        const rows = getPath(data, table.path);
        return [
          table.path,
          (Array.isArray(rows) ? rows : []).map((row) =>
            Object.fromEntries(table.columns.map((c) => [c.key, toText(getPath(row, c.key))])),
          ),
        ];
      }),
    ),
  };
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const NUMBER = /^-?\d+(\.\d+)?$/;

/** Why `text` isn't valid for `leaf`, or null (AC3). The server checks again. */
export function problemWith(leaf: Leaf, text: string): string | null {
  const value = text.trim();
  if (value === "") return null;
  if (leaf.kind === "number" && !NUMBER.test(value)) return "Enter a number, like 1250.50";
  if (leaf.kind === "date") {
    const parsed = new Date(`${value}T00:00:00Z`);
    if (
      !DATE.test(value) ||
      Number.isNaN(parsed.getTime()) ||
      !parsed.toISOString().startsWith(value)
    ) {
      return "Enter a date as YYYY-MM-DD";
    }
  }
  if (leaf.pattern && !new RegExp(leaf.pattern).test(value)) {
    return leaf.pattern.length > 20 ? "Not a valid GSTIN" : "Not in the expected format";
  }
  if (leaf.kind === "choice" && leaf.options && !leaf.options.includes(value)) {
    return `Choose one of ${leaf.options.join(", ")}`;
  }
  return null;
}

export function draftErrors(spec: FormSpec, draft: Draft): Record<string, string> {
  const errors: Record<string, string> = {};
  for (const field of spec.fields) {
    const problem = problemWith(field.leaf, draft.fields[field.path] ?? "");
    if (problem) errors[field.path] = problem;
  }
  for (const table of spec.tables) {
    (draft.tables[table.path] ?? []).forEach((row, index) => {
      for (const column of table.columns) {
        const problem = problemWith(column.leaf, row[column.key] ?? "");
        if (problem) errors[`${table.path}.${index}.${column.key}`] = problem;
      }
    });
  }
  return errors;
}

function fromText(leaf: Leaf, text: string): unknown {
  const value = text.trim();
  if (value === "") return null;
  return leaf.kind === "number" ? Number(value) : value;
}

function setPath(target: Data, path: string, value: unknown): void {
  const parts = path.split(".");
  let node = target;
  for (const part of parts.slice(0, -1)) {
    if (!isRecord(node[part])) node[part] = {};
    node = node[part] as Data;
  }
  node[parts.at(-1)!] = value;
}

/** An object whose fields are all empty becomes null when it was null (or absent) before,
 * so filling then clearing a field, or adding an empty row, gives what the model returns. */
function collapseEmpty(value: unknown, before: unknown): unknown {
  if (!isRecord(value)) return value;
  const entries = Object.entries(value).map(
    ([key, child]) => [key, collapseEmpty(child, isRecord(before) ? before[key] : null)] as const,
  );
  const empty = entries.every(([, child]) => child === null);
  return empty && (before === null || before === undefined) ? null : Object.fromEntries(entries);
}

/** The corrected instance: the original data with every form value written over it. */
export function dataFrom(spec: FormSpec, draft: Draft, original: Data): Data {
  const data: Data = structuredClone(original);
  for (const field of spec.fields) {
    setPath(data, field.path, fromText(field.leaf, draft.fields[field.path] ?? ""));
  }
  for (const key of Object.keys(data)) {
    if (!spec.tables.some((t) => t.path === key))
      data[key] = collapseEmpty(data[key], original[key]);
  }
  for (const table of spec.tables) {
    const before = getPath(original, table.path);
    data[table.path] = (draft.tables[table.path] ?? []).map((row, index) => {
      const item: Data = {};
      for (const column of table.columns) {
        setPath(item, column.key, fromText(column.leaf, row[column.key] ?? ""));
      }
      const beforeRow = Array.isArray(before) ? before[index] : undefined;
      return Object.fromEntries(
        Object.entries(item).map(([key, child]) => [
          key,
          collapseEmpty(child, isRecord(beforeRow) ? beforeRow[key] : null),
        ]),
      );
    });
  }
  return data;
}

export function emptyRow(table: TableSpec): Record<string, string> {
  return Object.fromEntries(table.columns.map((column) => [column.key, ""]));
}
