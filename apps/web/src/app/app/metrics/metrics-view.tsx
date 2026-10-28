"use client";

import { keepPreviousData, useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { DOC_TYPE_LABEL } from "@/components/doc-type";
import { STATUS_LABEL } from "@/components/document-status";
import { MeGate } from "@/components/me-gate";
import { Panel } from "@/components/page-header";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { currentWorkspace } from "@/lib/api/me";
import { fetchMetrics, metricsKeys, type Period, type WorkspaceMetrics } from "@/lib/api/metrics";

import { VolumeChart } from "./volume-chart";

const PERIODS: { value: Period; label: string }[] = [
  { value: "7d", label: "Last 7 days" },
  { value: "30d", label: "Last 30 days" },
  { value: "all", label: "All time" },
];
const TASK_LABEL: Record<string, string> = {
  classify: "Classify",
  extract: "Extract",
  validate: "Validate",
  embed: "Search index",
};
const DASH = "—";

export function percent(rate: number | null): string {
  return rate === null ? DASH : `${Math.round(rate * 100)}%`;
}

export function duration(seconds: number | null): string {
  if (seconds === null) return DASH;
  if (seconds < 60) return `${seconds < 10 ? seconds.toFixed(1) : Math.round(seconds)} s`;
  if (seconds < 3600) return `${(seconds / 60).toFixed(1)} min`;
  return `${(seconds / 3600).toFixed(1)} h`;
}

export function usd(value: number | null): string {
  if (value === null) return DASH;
  if (value === 0) return "$0";
  return `$${value >= 0.01 ? value.toFixed(2) : value.toPrecision(2)}`;
}

/** The workspace's metrics for a chosen period (F13). */
export function MetricsView() {
  return (
    <MeGate>
      {(me) => {
        const membership = currentWorkspace(me);
        if (membership === undefined) {
          return (
            <p className="text-sm text-muted-foreground">
              You don&apos;t belong to a workspace yet.
            </p>
          );
        }
        return <WorkspaceMetricsView workspaceId={membership.workspace.id} />;
      }}
    </MeGate>
  );
}

function WorkspaceMetricsView({ workspaceId }: { workspaceId: string }) {
  const [period, setPeriod] = useState<Period>("30d");
  const metrics = useQuery({
    queryKey: metricsKeys.period(workspaceId, period),
    queryFn: () => fetchMetrics(workspaceId, period),
    placeholderData: keepPreviousData,
  });
  return (
    <div className="flex flex-col gap-5">
      <Tabs value={period} onValueChange={(value) => setPeriod(value as Period)}>
        <TabsList aria-label="Period">
          {PERIODS.map(({ value, label }) => (
            <TabsTrigger key={value} value={value} className="px-3">
              {label}
            </TabsTrigger>
          ))}
        </TabsList>
      </Tabs>
      {metrics.isPending ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : metrics.isError ? (
        <p role="alert" className="text-sm text-destructive">
          Couldn&apos;t load the metrics. Try again in a moment.
        </p>
      ) : (
        <Figures metrics={metrics.data} />
      )}
    </div>
  );
}

function Figures({ metrics }: { metrics: WorkspaceMetrics }) {
  const { headline, volume, llm, queue } = metrics;
  const uploaded = Object.values(volume.by_status).reduce((sum, count) => sum + count, 0);
  const tiles = [
    {
      label: "Approved without edits",
      value: percent(headline.approved_without_edits_rate),
      note: `${headline.approved_without_edits} of ${headline.approved} approved · ${headline.approved_by_agent} by the agent`,
    },
    {
      label: "Field accuracy",
      value: percent(headline.field_accuracy),
      note: `${headline.fields_unchanged} of ${headline.fields_reviewed} fields unchanged by reviewers`,
    },
    {
      label: "Cost per document",
      value: usd(headline.cost_per_document_usd),
      note: `${usd(headline.cost_usd)} for ${headline.documents_processed} documents · estimated at list prices; your provider bills you`,
    },
    {
      label: "Processing time",
      value: duration(headline.processing_seconds_p50),
      note: `median · 95th percentile ${duration(headline.processing_seconds_p95)} · ${headline.processing_runs} runs`,
    },
  ];
  return (
    <>
      <Panel>
        <dl className="grid gap-6 sm:grid-cols-2 lg:grid-cols-4">
          {tiles.map((tile) => (
            <div key={tile.label}>
              <dt className="text-sm text-muted-foreground">{tile.label}</dt>
              <dd className="mt-1 text-3xl font-semibold tracking-tight tabular-nums">
                {tile.value}
              </dd>
              <dd className="text-xs text-muted-foreground">{tile.note}</dd>
            </div>
          ))}
        </dl>
      </Panel>
      <Panel>
        {uploaded === 0 ? (
          <p className="text-sm text-muted-foreground">No documents in this period.</p>
        ) : (
          <div className="grid gap-8 lg:grid-cols-[2fr_1fr]">
            <VolumeChart days={volume.per_day} />
            <div className="grid grid-cols-2 gap-6 text-sm lg:grid-cols-1">
              <Counts
                title="By status now"
                counts={Object.entries(volume.by_status).map(([status, count]) => [
                  STATUS_LABEL[status as keyof typeof STATUS_LABEL] ?? status,
                  count,
                ])}
              />
              <Counts
                title="By type"
                counts={Object.entries(volume.by_doc_type).map(([docType, count]) => [
                  DOC_TYPE_LABEL[docType as keyof typeof DOC_TYPE_LABEL] ?? "Unclassified",
                  count,
                ])}
              />
            </div>
          </div>
        )}
      </Panel>
      <div className="grid gap-5 lg:grid-cols-[2fr_1fr]">
        <Panel>
          <h2 className="mb-4 text-lg font-semibold">AI providers</h2>
          <LlmTable tasks={llm} />
        </Panel>
        <Panel>
          <h2 className="mb-4 text-lg font-semibold">Queue</h2>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm">
            <dt className="text-muted-foreground">Waiting</dt>
            <dd className="tabular-nums">{queue.queued}</dd>
            <dt className="text-muted-foreground">Running</dt>
            <dd className="tabular-nums">{queue.running}</dd>
            <dt className="text-muted-foreground">Gave up</dt>
            <dd className="tabular-nums">{queue.dead}</dd>
            <dt className="text-muted-foreground">Oldest waiting</dt>
            <dd className="tabular-nums">{duration(queue.oldest_queued_seconds)}</dd>
            <dt className="text-muted-foreground">Failed in period</dt>
            <dd className="tabular-nums">{queue.failed}</dd>
          </dl>
          {queue.failure_reasons.length > 0 && (
            <ul className="mt-4 divide-y border-t text-sm">
              {queue.failure_reasons.map((failure) => (
                <li key={failure.reason} className="flex justify-between gap-4 py-2">
                  <span className="min-w-0 truncate">{failure.reason}</span>
                  <span className="text-muted-foreground tabular-nums">{failure.documents}</span>
                </li>
              ))}
            </ul>
          )}
        </Panel>
      </div>
    </>
  );
}

function Counts({ title, counts }: { title: string; counts: [string, number][] }) {
  const shown = counts.filter(([, count]) => count > 0);
  return (
    <div>
      <h3 className="mb-2 font-medium">{title}</h3>
      <dl className="grid grid-cols-[1fr_auto] gap-x-4 gap-y-1">
        {shown.map(([label, count]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd className="text-right tabular-nums">{count}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}

function outcome(task: WorkspaceMetrics["llm"][number], name: string): number {
  return task.outcomes[name] ?? 0;
}

function LlmTable({ tasks }: { tasks: WorkspaceMetrics["llm"] }) {
  const used = tasks.filter((task) => task.calls > 0);
  if (used.length === 0) {
    return <p className="text-sm text-muted-foreground">No AI calls in this period.</p>;
  }
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-muted-foreground">
          <tr>
            <th scope="col" className="py-2 pr-4 font-normal">
              Task
            </th>
            <th scope="col" className="py-2 pr-4 text-right font-normal">
              Calls
            </th>
            <th scope="col" className="py-2 pr-4 text-right font-normal">
              Answered
            </th>
            <th scope="col" className="py-2 pr-4 text-right font-normal">
              Failed
            </th>
            <th scope="col" className="py-2 pr-4 text-right font-normal">
              Fallbacks
            </th>
            <th scope="col" className="py-2 pr-4 text-right font-normal">
              Median time
            </th>
            <th scope="col" className="py-2 font-normal">
              Mostly served by
            </th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {used.map((task) => {
            const answered = outcome(task, "ok") + outcome(task, "cache_hit");
            const failed = outcome(task, "error") + outcome(task, "invalid_output");
            const top = task.served_by[0];
            return (
              <tr key={task.task}>
                <th scope="row" className="py-2 pr-4 text-left font-medium">
                  {TASK_LABEL[task.task] ?? task.task}
                </th>
                <td className="py-2 pr-4 text-right tabular-nums">{task.calls}</td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {answered}
                  {outcome(task, "cache_hit") > 0 && (
                    <span className="text-muted-foreground">
                      {" "}
                      ({outcome(task, "cache_hit")} cached)
                    </span>
                  )}
                </td>
                <td className="py-2 pr-4 text-right tabular-nums">{failed}</td>
                <td className="py-2 pr-4 text-right tabular-nums">{percent(task.fallback_rate)}</td>
                <td className="py-2 pr-4 text-right tabular-nums">
                  {task.latency_ms_p50 === null ? DASH : duration(task.latency_ms_p50 / 1000)}
                </td>
                <td className="py-2">
                  {top ? (
                    <span>
                      {top.provider} · {top.model}{" "}
                      <span className="text-muted-foreground">
                        {percent(answered ? top.calls / answered : null)}
                      </span>
                    </span>
                  ) : (
                    DASH
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
