"use client";

import { SearchIcon, SlidersHorizontalIcon, XIcon } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { activeParams, EMPTY_SEARCH, type SearchParams } from "@/lib/api/search";

const TYPES = [
  ["invoice", "Invoice"],
  ["receipt", "Receipt"],
  ["purchase_order", "Purchase order"],
  ["other", "Other"],
] as const;
const STATUSES = [
  ["NEEDS_REVIEW", "Needs review"],
  ["APPROVED", "Approved"],
  ["FAILED", "Failed"],
  ["UPLOADED", "Queued"],
] as const;

const SELECT =
  "h-10 w-full rounded-xl border border-input bg-transparent px-2 text-sm dark:bg-input/30";

/** Search text plus the filters of F8 AC4. */
export function SearchBar({
  value,
  onChange,
}: {
  value: SearchParams;
  onChange: (value: SearchParams) => void;
}) {
  const filterCount = Object.keys(activeParams({ ...value, q: "" })).length;
  const [open, setOpen] = useState(filterCount > 0);
  const set = (key: keyof SearchParams) => (next: string) => onChange({ ...value, [key]: next });

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <div className="relative flex-1">
          <SearchIcon
            className="pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2 text-muted-foreground"
            aria-hidden
          />
          <Input
            type="search"
            aria-label="Search documents"
            placeholder="Search by number, vendor, GSTIN, item, or describe it in words"
            value={value.q}
            onChange={(event) => set("q")(event.target.value)}
            className="pl-9"
          />
        </div>
        <Button variant="outline" onClick={() => setOpen(!open)} aria-expanded={open}>
          <SlidersHorizontalIcon aria-hidden />
          Filters{filterCount > 0 ? ` (${filterCount})` : ""}
        </Button>
        {(filterCount > 0 || value.q) && (
          <Button variant="ghost" onClick={() => onChange(EMPTY_SEARCH)}>
            <XIcon aria-hidden />
            Clear
          </Button>
        )}
      </div>
      {open && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Type</span>
            <select
              className={SELECT}
              value={value.doc_type}
              onChange={(e) => set("doc_type")(e.target.value)}
            >
              <option value="">Any</option>
              {TYPES.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Status</span>
            <select
              className={SELECT}
              value={value.status}
              onChange={(e) => set("status")(e.target.value)}
            >
              <option value="">Any</option>
              {STATUSES.map(([key, label]) => (
                <option key={key} value={key}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Vendor</span>
            <Input value={value.vendor} onChange={(e) => set("vendor")(e.target.value)} />
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">Total from</span>
              <Input
                inputMode="decimal"
                value={value.amount_min}
                onChange={(e) => set("amount_min")(e.target.value)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm">
              <span className="text-muted-foreground">to</span>
              <Input
                inputMode="decimal"
                value={value.amount_max}
                onChange={(e) => set("amount_max")(e.target.value)}
              />
            </label>
          </div>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Dated from</span>
            <Input
              type="date"
              value={value.date_from}
              onChange={(e) => set("date_from")(e.target.value)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            <span className="text-muted-foreground">Dated to</span>
            <Input
              type="date"
              value={value.date_to}
              onChange={(e) => set("date_to")(e.target.value)}
            />
          </label>
        </div>
      )}
    </div>
  );
}
