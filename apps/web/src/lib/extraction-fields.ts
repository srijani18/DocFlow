/**
 * Turns an extraction's `data` into rows and tables for display, without knowing the
 * document type: the shape comes from the JSON Schema it was validated against (F5).
 * Paths use the same dotted, zero-based form as the confidence map.
 */

export type Scalar = string | number | boolean | null;
export type FieldRow = { path: string; label: string; value: Scalar };
export type TableSection = {
  path: string;
  label: string;
  columns: { key: string; label: string }[];
  rows: { path: string; cells: Record<string, Scalar> }[];
};

const SPECIAL_LABELS: Record<string, string> = {
  gstin: "GSTIN",
  hsn_sac: "HSN/SAC",
  po_number: "PO number",
  po_date: "PO date",
};

export function humanize(key: string): string {
  if (key in SPECIAL_LABELS) return SPECIAL_LABELS[key]!;
  const words = key.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Leaves of a nested object: { unit_price: { amount: 1 } } → [["unit_price.amount", 1]]. */
function leaves(value: unknown, prefix: string): [string, Scalar][] {
  if (isRecord(value)) {
    return Object.entries(value).flatMap(([key, child]) =>
      leaves(child, prefix ? `${prefix}.${key}` : key),
    );
  }
  if (Array.isArray(value)) {
    return [[prefix, value.length === 0 ? null : JSON.stringify(value)]];
  }
  return [[prefix, value as Scalar]];
}

function leafLabel(path: string): string {
  return path.split(".").map(humanize).join(" › ");
}

export function layoutFields(data: Record<string, unknown>): {
  fields: FieldRow[];
  tables: TableSection[];
} {
  const fields: FieldRow[] = [];
  const tables: TableSection[] = [];
  for (const [key, value] of Object.entries(data)) {
    if (Array.isArray(value) && value.every(isRecord)) {
      const rows = value.map((item, index) => ({
        path: `${key}.${index}`,
        cells: Object.fromEntries(leaves(item, "")),
      }));
      const columnKeys = [...new Set(rows.flatMap((row) => Object.keys(row.cells)))];
      tables.push({
        path: key,
        label: humanize(key),
        columns: columnKeys.map((column) => ({ key: column, label: leafLabel(column) })),
        rows,
      });
      continue;
    }
    for (const [path, leaf] of leaves(value, key)) {
      fields.push({ path, label: leafLabel(path), value: leaf });
    }
  }
  return { fields, tables };
}
