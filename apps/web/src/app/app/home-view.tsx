"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRightIcon, CloudUploadIcon, KeyRoundIcon } from "lucide-react";
import Link from "next/link";

import { DocTypeLabel } from "@/components/doc-type";
import { DocumentStatusBadge } from "@/components/document-status";
import { MeGate } from "@/components/me-gate";
import { PageHeader, Panel } from "@/components/page-header";
import { buttonVariants } from "@/components/ui/button";
import type { components } from "@/generated/api";
import { aiKeyKeys, fetchAiKeys } from "@/lib/api/ai-keys";
import { documentKeys, fetchDocumentPage } from "@/lib/api/documents";
import { currentWorkspace, type Me } from "@/lib/api/me";
import { fetchReviewMetrics } from "@/lib/api/review";
import { formatMoney } from "@/lib/format";

type Role = components["schemas"]["Role"];

const ROLE_LABEL: Record<Role, string> = { admin: "Admin", reviewer: "Reviewer" };
const RECENT_COUNT = 5;

/** The app home: who is signed in, their workspace and role (F1 AC10), plus recent work. */
export function HomeView() {
  return <MeGate>{(me) => <Dashboard me={me} />}</MeGate>;
}

function Dashboard({ me }: { me: Me }) {
  const membership = currentWorkspace(me);
  const name = me.user.display_name ?? me.user.email ?? "there";
  return (
    <div className="flex flex-col gap-8">
      <PageHeader
        title={
          <>
            Welcome back, <span className="text-brand-gradient">{name.split("@")[0]}</span>
          </>
        }
        description="Here's what's happening in your workspace."
      />
      {membership !== undefined && <ConnectKeyBanner workspaceId={membership.workspace.id} />}
      <div className="grid gap-5 lg:grid-cols-[1fr_1fr]">
        <Panel>
          <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-3 text-sm">
            <dt className="text-muted-foreground">Signed in as</dt>
            <dd className="font-medium">
              {me.user.email ?? me.user.display_name ?? "Your account"}
            </dd>
            {membership === undefined ? (
              <dd className="col-span-2">You don&apos;t belong to a workspace yet.</dd>
            ) : (
              <>
                <dt className="text-muted-foreground">Workspace</dt>
                <dd className="font-medium">{membership.workspace.name}</dd>
                <dt className="text-muted-foreground">Your role</dt>
                <dd>
                  <span className="rounded-full bg-accent px-2.5 py-0.5 text-xs font-semibold text-accent-foreground">
                    {ROLE_LABEL[membership.role]}
                  </span>
                </dd>
              </>
            )}
          </dl>
        </Panel>
        {membership !== undefined && (
          <div className="bg-brand-gradient flex flex-col justify-between gap-6 rounded-3xl p-6 text-white shadow-xl shadow-primary/20">
            <div className="flex items-center gap-3">
              <span className="inline-flex size-11 items-center justify-center rounded-xl bg-white text-indigo-600">
                <CloudUploadIcon className="size-5" aria-hidden />
              </span>
              <h2 className="text-xl font-semibold">Upload documents</h2>
            </div>
            <p className="text-white/85">
              Drop invoices, receipts or purchase orders. DocFlow classifies them and extracts their
              fields in seconds.
            </p>
            <Link
              href="/app/documents"
              className={`${buttonVariants({ variant: "subtle", size: "lg" })} w-fit text-foreground`}
            >
              Go to documents <ArrowRightIcon aria-hidden />
            </Link>
          </div>
        )}
      </div>
      {membership !== undefined && <ReviewMetricsPanel workspaceId={membership.workspace.id} />}
      {membership !== undefined && <RecentDocuments workspaceId={membership.workspace.id} />}
    </div>
  );
}

/** How much of the approved work needed a person to change something (F7 AC8). */
function ReviewMetricsPanel({ workspaceId }: { workspaceId: string }) {
  const metrics = useQuery({
    queryKey: [...documentKeys.list(workspaceId), "review-metrics"],
    queryFn: () => fetchReviewMetrics(workspaceId),
  });
  if (!metrics.isSuccess) return null;
  const { approved, approved_without_edits, approved_by_agent, approved_without_edits_rate } =
    metrics.data;
  const tiles = [
    {
      label: "Approved without edits",
      value:
        approved_without_edits_rate === null
          ? "—"
          : `${Math.round(approved_without_edits_rate * 100)}%`,
      note: `${approved_without_edits} of ${approved} approved`,
    },
    { label: "Approved", value: String(approved), note: "documents ready for export" },
    {
      label: "Approved by the agent",
      value: String(approved_by_agent),
      note: "every check passed, high confidence",
    },
  ];
  return (
    <Panel>
      <dl className="grid gap-6 sm:grid-cols-3">
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
  );
}

function RecentDocuments({ workspaceId }: { workspaceId: string }) {
  // Shares the documents list cache, so the Documents page opens instantly afterwards.
  const recent = useQuery({
    queryKey: [...documentKeys.list(workspaceId), "recent"],
    queryFn: () => fetchDocumentPage(workspaceId, null),
  });
  const items = recent.data?.items.slice(0, RECENT_COUNT) ?? [];
  return (
    <Panel>
      <div className="mb-4 flex items-center justify-between">
        <h2 className="text-lg font-semibold">Recent documents</h2>
        <Link href="/app/documents" className="text-sm font-medium text-primary hover:underline">
          View all
        </Link>
      </div>
      {recent.isPending ? (
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-muted-foreground">
          No documents yet. Upload one to get started.
        </p>
      ) : (
        <ul className="divide-y">
          {items.map((document) => (
            <li
              key={document.id}
              className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm"
            >
              <Link
                href={`/app/documents/${document.id}`}
                className="min-w-0 flex-1 truncate font-medium hover:underline"
              >
                {document.filename}
              </Link>
              <span className="hidden text-muted-foreground sm:inline">
                <DocTypeLabel docType={document.doc_type} confidence={null} />
              </span>
              <span className="w-28 text-right tabular-nums">
                {formatMoney(document.total_amount, document.currency)}
              </span>
              <DocumentStatusBadge status={document.status} />
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

/** Shown until the workspace connects an AI provider: nothing is processed before then (F15). */
function ConnectKeyBanner({ workspaceId }: { workspaceId: string }) {
  const keys = useQuery({
    queryKey: aiKeyKeys.list(workspaceId),
    queryFn: () => fetchAiKeys(workspaceId),
  });
  if (!keys.isSuccess || keys.data.some((key) => key.connected && key.status !== "rejected")) {
    return null;
  }
  return (
    <div className="bg-brand-gradient flex flex-col items-start justify-between gap-4 rounded-3xl p-6 text-white shadow-lg shadow-primary/20 sm:flex-row sm:items-center">
      <div className="flex items-center gap-3">
        <span className="inline-flex size-10 items-center justify-center rounded-xl bg-white text-indigo-600">
          <KeyRoundIcon className="size-5" aria-hidden />
        </span>
        <div>
          <p className="font-semibold">Connect an AI provider to start processing</p>
          <p className="text-sm text-white/85">
            DocFlow runs on your own Gemini, Groq or OpenRouter key.
          </p>
        </div>
      </div>
      <Link
        href="/app/settings"
        className={`${buttonVariants({ variant: "subtle" })} text-foreground`}
      >
        Connect a key <ArrowRightIcon aria-hidden />
      </Link>
    </div>
  );
}
