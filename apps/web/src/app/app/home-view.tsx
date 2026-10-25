"use client";

import Link from "next/link";

import { MeGate } from "@/components/me-gate";
import type { components } from "@/generated/api";
import { currentWorkspace, type Me } from "@/lib/api/me";

type Role = components["schemas"]["Role"];

const ROLE_LABEL: Record<Role, string> = { admin: "Admin", reviewer: "Reviewer" };

/** The app home: who is signed in, their workspace and role (F1 AC10). */
export function HomeView() {
  return <MeGate>{(me) => <Account me={me} />}</MeGate>;
}

function Account({ me }: { me: Me }) {
  const membership = currentWorkspace(me);
  return (
    <div className="flex flex-col gap-6">
      <dl className="grid grid-cols-[auto_1fr] gap-x-6 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Signed in as</dt>
        <dd>{me.user.email ?? me.user.display_name ?? "Your account"}</dd>
        {membership === undefined ? (
          <dd className="col-span-2">You don&apos;t belong to a workspace yet.</dd>
        ) : (
          <>
            <dt className="text-muted-foreground">Workspace</dt>
            <dd>{membership.workspace.name}</dd>
            <dt className="text-muted-foreground">Your role</dt>
            <dd>{ROLE_LABEL[membership.role]}</dd>
          </>
        )}
      </dl>
      {membership !== undefined && (
        <Link href="/app/documents" className="text-sm font-medium underline underline-offset-4">
          Go to documents
        </Link>
      )}
    </div>
  );
}
