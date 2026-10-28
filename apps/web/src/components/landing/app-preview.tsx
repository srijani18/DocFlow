import { ClockIcon, FileTextIcon, LayoutGridIcon, ListChecksIcon, SearchIcon } from "lucide-react";

import { LogoMark } from "@/components/brand";
import { Sparkline } from "@/components/landing/sparkline";

const STATS = [
  {
    label: "Documents processed",
    value: "1 284",
    change: "+12.4%",
    points: [3, 5, 4, 7, 6, 9, 8, 12],
  },
  {
    label: "Fields extracted",
    value: "26 913",
    change: "+9.1%",
    points: [4, 4, 6, 5, 8, 7, 10, 11],
  },
  {
    label: "Approved without edits",
    value: "87%",
    change: "+3.2%",
    points: [5, 6, 5, 7, 7, 8, 9, 9],
  },
];

const ROWS = [
  {
    name: "INV-2026-0142.pdf",
    type: "Invoice",
    vendor: "Kaveri Fasteners",
    total: "₹16,826.80",
    status: "Needs review",
  },
  {
    name: "receipt-0902.jpg",
    type: "Receipt",
    vendor: "Annapurna Tiffin",
    total: "₹346.50",
    status: "Approved",
  },
  {
    name: "PO-7781.pdf",
    type: "Purchase order",
    vendor: "Sahyadri Build",
    total: "₹48,200.00",
    status: "Extracting",
  },
];

const MIX = [
  { label: "Invoices", share: 62 },
  { label: "Receipts", share: 25 },
  { label: "Purchase orders", share: 13 },
];

const STATUS_TONE: Record<string, string> = {
  "Needs review": "bg-amber-50 text-amber-700 dark:bg-amber-950 dark:text-amber-300",
  Approved: "bg-emerald-50 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300",
  Extracting: "bg-indigo-50 text-indigo-700 dark:bg-indigo-950 dark:text-indigo-300",
};

/** A static picture of the app for the landing page, with illustrative numbers. */
export function AppPreview() {
  return (
    <div
      className="overflow-hidden rounded-3xl border bg-card text-left shadow-2xl shadow-primary/10"
      aria-label="Preview of the DocFlow app (illustrative data)"
      role="img"
    >
      <div className="flex">
        <aside className="hidden w-48 shrink-0 flex-col gap-1 border-r p-4 text-xs sm:flex">
          <div className="mb-4 flex items-center gap-2">
            <LogoMark size="sm" />
            <span className="text-sm font-semibold">DocFlow</span>
          </div>
          {[
            { icon: LayoutGridIcon, label: "Dashboard", active: true },
            { icon: FileTextIcon, label: "Documents" },
            { icon: ListChecksIcon, label: "Review" },
            { icon: SearchIcon, label: "Search" },
            { icon: ClockIcon, label: "Activity" },
          ].map(({ icon: Icon, label, active }) => (
            <span
              key={label}
              className={`flex items-center gap-2 rounded-lg px-2.5 py-2 ${active ? "bg-accent font-medium text-accent-foreground" : "text-muted-foreground"}`}
            >
              <Icon className="size-3.5" />
              {label}
            </span>
          ))}
        </aside>
        <div className="min-w-0 flex-1 bg-surface p-4">
          <div className="mb-4 flex items-center justify-between gap-3">
            <span className="flex h-8 flex-1 items-center gap-2 rounded-full border bg-card px-3 text-[11px] text-muted-foreground">
              <SearchIcon className="size-3" /> Search documents, vendors, GSTINs…
            </span>
            <span className="flex items-center gap-2 text-[11px]">
              <span className="bg-brand-gradient size-7 rounded-full" />
              <span className="hidden flex-col leading-tight md:flex">
                <span className="font-medium">Ananya Rao</span>
                <span className="text-muted-foreground">Admin</span>
              </span>
            </span>
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3">
            {STATS.map((stat, index) => (
              <div
                key={stat.label}
                className="flex items-end justify-between rounded-2xl bg-card p-3 shadow-sm"
              >
                <div>
                  <p className="text-[11px] text-muted-foreground">{stat.label}</p>
                  <p className="mt-1 text-xl font-semibold tracking-tight">{stat.value}</p>
                  <p className="text-[10px] font-medium text-emerald-600 dark:text-emerald-400">
                    {stat.change} ↗
                  </p>
                </div>
                <Sparkline id={`preview-${index}`} points={stat.points} />
              </div>
            ))}
          </div>
          <div className="mt-3 grid grid-cols-1 gap-3 lg:grid-cols-[1.6fr_1fr]">
            <div className="rounded-2xl bg-card p-3 shadow-sm">
              <p className="mb-2 text-xs font-medium">Recent documents</p>
              <table className="w-full text-[11px]">
                <tbody>
                  {ROWS.map((row) => (
                    <tr key={row.name} className="border-t first:border-t-0">
                      <td className="py-2 pr-2 font-medium">{row.name}</td>
                      <td className="hidden py-2 pr-2 text-muted-foreground md:table-cell">
                        {row.vendor}
                      </td>
                      <td className="py-2 pr-2 text-right tabular-nums">{row.total}</td>
                      <td className="py-2 text-right">
                        <span
                          className={`rounded-full px-2 py-0.5 text-[10px] font-medium ${STATUS_TONE[row.status]}`}
                        >
                          {row.status}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="rounded-2xl bg-card p-3 shadow-sm">
              <p className="mb-3 text-xs font-medium">Document mix</p>
              <div className="flex flex-col gap-3">
                {MIX.map((item) => (
                  <div key={item.label} className="text-[11px]">
                    <div className="mb-1 flex justify-between">
                      <span>{item.label}</span>
                      <span className="text-muted-foreground">{item.share}%</span>
                    </div>
                    <div className="h-1.5 rounded-full bg-muted">
                      <div
                        className="bg-brand-gradient h-1.5 rounded-full"
                        style={{ width: `${item.share}%` }}
                      />
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
