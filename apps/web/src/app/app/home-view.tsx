"use client";

import { useQuery } from "@tanstack/react-query";
import { ArrowRightIcon, CloudUploadIcon } from "lucide-react";
import Link from "next/link";

import { DocTypeLabel } from "@/components/doc-type";
import { DocumentStatusBadge } from "@/components/document-status";
import { MeGate } from "@/components/me-gate";
import { PageHeader, Panel } from "@/components/page-header";
import { buttonVariants } from "@/components/ui/button";
import type { components } from "@/generated/api";
import { documentKeys, fetchDocumentPage } from "@/lib/api/documents";
import { currentWorkspace, type Me } from "@/lib/api/me";
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
              <span className="inline-flex size-11 items-center justify-center rounded-xl bg-white text-primary">
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
      {membership !== undefined && <RecentDocuments workspaceId={membership.workspace.id} />}
    </div>
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
