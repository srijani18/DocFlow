import { dataFrom, draftErrors, draftFrom, emptyRow, formSpec } from "./form";

const MONEY = {
  anyOf: [
    {
      type: "object",
      properties: {
        amount: { type: ["number", "null"] },
        currency: { type: ["string", "null"], pattern: "^[A-Z]{3}$" },
      },
    },
    { type: "null" },
  ],
};
const GSTIN = "^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][1-9A-Z]Z[0-9A-Z]$";
const SCHEMA = {
  type: "object",
  properties: {
    invoice_number: { type: ["string", "null"] },
    invoice_date: { type: ["string", "null"], format: "date" },
    vendor: {
      anyOf: [
        {
          type: "object",
          properties: {
            name: { type: ["string", "null"] },
            gstin: { type: ["string", "null"], pattern: GSTIN },
          },
        },
        { type: "null" },
      ],
    },
    line_items: {
      type: "array",
      items: {
        type: "object",
        properties: { description: { type: ["string", "null"] }, amount: MONEY },
      },
    },
    taxes: {
      type: "array",
      items: {
        type: "object",
        properties: {
          type: { anyOf: [{ type: "string", enum: ["CGST", "SGST", "IGST"] }, { type: "null" }] },
        },
      },
    },
    total: MONEY,
  },
};
const DATA = {
  invoice_number: "INV-1",
  invoice_date: "2026-08-14",
  vendor: { name: "Kaveri", gstin: "29ABCDE1234F1Z5" },
  line_items: [{ description: "Bolts", amount: { amount: 480, currency: "INR" } }],
  taxes: [{ type: "CGST" }],
  total: { amount: 16826.8, currency: "INR" },
};

describe("formSpec", () => {
  it("F7 D2: fields and tables come from the schema", () => {
    const spec = formSpec(SCHEMA);

    expect(spec.fields.map((f) => [f.path, f.label, f.leaf.kind])).toEqual([
      ["invoice_number", "Invoice number", "text"],
      ["invoice_date", "Invoice date", "date"],
      ["vendor.name", "Vendor › Name", "text"],
      ["vendor.gstin", "Vendor › GSTIN", "text"],
      ["total.amount", "Total › Amount", "number"],
      ["total.currency", "Total › Currency", "text"],
    ]);
    expect(spec.tables.map((t) => [t.path, t.columns.map((c) => c.key)])).toEqual([
      ["line_items", ["description", "amount.amount", "amount.currency"]],
      ["taxes", ["type"]],
    ]);
    expect(spec.tables[1]!.columns[0]!.leaf).toEqual({
      kind: "choice",
      options: ["CGST", "SGST", "IGST"],
    });
  });
});

describe("draft round trip", () => {
  const spec = formSpec(SCHEMA);

  it("an untouched form gives back the original data", () => {
    expect(dataFrom(spec, draftFrom(spec, DATA), DATA)).toEqual(DATA);
  });

  it("edits become typed values; a cleared field becomes null", () => {
    const draft = draftFrom(spec, DATA);
    draft.fields["total.amount"] = "16826.85";
    draft.fields["invoice_number"] = "";

    const data = dataFrom(spec, draft, DATA);

    expect(data.total).toEqual({ amount: 16826.85, currency: "INR" });
    expect(data.invoice_number).toBeNull();
  });

  it("an added empty row has null objects, as the model returns them", () => {
    const draft = draftFrom(spec, DATA);
    draft.tables.line_items!.push(emptyRow(spec.tables[0]!));

    const data = dataFrom(spec, draft, DATA);

    expect((data.line_items as unknown[])[1]).toEqual({ description: null, amount: null });
  });

  it("filling a field of a missing object creates the object", () => {
    const original = { ...DATA, vendor: null };
    const draft = draftFrom(spec, original);
    draft.fields["vendor.name"] = "Narmada";

    expect(dataFrom(spec, draft, original).vendor).toEqual({ name: "Narmada", gstin: null });
  });
});

describe("draftErrors", () => {
  const spec = formSpec(SCHEMA);

  it("AC3: dates, numbers and GSTINs are checked as you type", () => {
    const draft = draftFrom(spec, DATA);
    draft.fields["invoice_date"] = "14-08-2026";
    draft.fields["total.amount"] = "16,826.80";
    draft.fields["vendor.gstin"] = "29ABCDE1234F1Z";
    draft.tables.line_items![0]!["amount.amount"] = "abc";

    expect(draftErrors(spec, draft)).toEqual({
      invoice_date: "Enter a date as YYYY-MM-DD",
      "total.amount": "Enter a number, like 1250.50",
      "vendor.gstin": "Not a valid GSTIN",
      "line_items.0.amount.amount": "Enter a number, like 1250.50",
    });
  });

  it("rejects impossible dates and accepts empty fields", () => {
    const draft = draftFrom(spec, DATA);
    draft.fields["invoice_date"] = "2026-02-30";
    draft.fields["vendor.gstin"] = "";

    expect(draftErrors(spec, draft)).toEqual({ invoice_date: "Enter a date as YYYY-MM-DD" });
  });
});
