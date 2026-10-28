"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ExternalLinkIcon, KeyRoundIcon, ShieldCheckIcon } from "lucide-react";
import { useState, type FormEvent } from "react";

import { MeGate } from "@/components/me-gate";
import { Panel } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  PROVIDERS,
  aiKeyKeys,
  deleteAiKey,
  fetchAiKeys,
  saveAiKey,
  testAiKey,
  type AiKeyStatus,
  type Provider,
} from "@/lib/api/ai-keys";
import { currentWorkspace } from "@/lib/api/me";
import { ApiError } from "@/lib/api/transient";
import { formatDateTime } from "@/lib/format";

export function AiKeysView() {
  return (
    <MeGate>
      {(me) => {
        const membership = currentWorkspace(me);
        if (membership === undefined) {
          return <p className="text-sm">You don&apos;t belong to a workspace yet.</p>;
        }
        return (
          <AiKeys workspaceId={membership.workspace.id} isAdmin={membership.role === "admin"} />
        );
      }}
    </MeGate>
  );
}

/** The workspace's own AI provider keys (F15). Admins manage them; everyone sees status. */
export function AiKeys({ workspaceId, isAdmin }: { workspaceId: string; isAdmin: boolean }) {
  const keys = useQuery({
    queryKey: aiKeyKeys.list(workspaceId),
    queryFn: () => fetchAiKeys(workspaceId),
  });
  if (keys.isPending) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (keys.isError) {
    return (
      <p role="alert" className="text-sm text-destructive">
        Couldn&apos;t load AI keys.
      </p>
    );
  }
  const byProvider = new Map(keys.data.map((status) => [status.provider, status]));
  return (
    <div className="flex flex-col gap-5">
      <Panel className="flex items-start gap-4 bg-accent/60">
        <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-xl bg-card text-primary">
          <ShieldCheckIcon className="size-5" aria-hidden />
        </span>
        <p className="text-sm text-foreground/80">
          DocFlow uses <strong>your own</strong> AI provider keys: processing runs on your account
          and quota. Keys are checked when saved, encrypted at rest and never shown again. Only the
          last 4 characters are displayed.
          {!isAdmin && " Only workspace admins can add or change keys."}
        </p>
      </Panel>
      {PROVIDERS.map((provider) => (
        <ProviderCard
          key={provider.id}
          workspaceId={workspaceId}
          provider={provider}
          status={byProvider.get(provider.id)}
          isAdmin={isAdmin}
        />
      ))}
    </div>
  );
}

function describe(error: unknown): string {
  if (error instanceof ApiError)
    return error.problem?.detail ?? error.problem?.title ?? "Something went wrong.";
  return "Couldn't reach DocFlow. Try again.";
}

function StatusPill({ status }: { status: AiKeyStatus | undefined }) {
  if (!status?.connected) {
    return (
      <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-medium text-muted-foreground">
        Not connected
      </span>
    );
  }
  if (status.status === "rejected") {
    return (
      <span className="rounded-full bg-red-50 px-2.5 py-0.5 text-xs font-medium text-red-700 dark:bg-red-950 dark:text-red-300">
        Key rejected
      </span>
    );
  }
  return (
    <span className="rounded-full bg-emerald-50 px-2.5 py-0.5 text-xs font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
      Connected · …{status.last4}
    </span>
  );
}

function ProviderCard({
  workspaceId,
  provider,
  status,
  isAdmin,
}: {
  workspaceId: string;
  provider: (typeof PROVIDERS)[number];
  status: AiKeyStatus | undefined;
  isAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [key, setKey] = useState("");
  const refresh = () => queryClient.invalidateQueries({ queryKey: aiKeyKeys.list(workspaceId) });
  const id: Provider = provider.id;

  const save = useMutation({
    mutationFn: () => saveAiKey(workspaceId, id, key),
    onSuccess: () => {
      setKey("");
      setEditing(false);
      void refresh();
      // Documents waiting for a key are requeued by the server (F15 AC8).
      void queryClient.invalidateQueries({ queryKey: ["documents", workspaceId] });
    },
  });
  const remove = useMutation({
    mutationFn: () => deleteAiKey(workspaceId, id),
    onSuccess: () => void refresh(),
  });
  const test = useMutation({
    mutationFn: () => testAiKey(workspaceId, id),
    onSuccess: () => void refresh(),
  });
  const error = save.error ?? remove.error ?? test.error;

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    save.mutate();
  }

  return (
    <Panel>
      <section aria-label={provider.name} className="flex flex-col gap-4">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="flex items-center gap-3">
            <span className="bg-brand-gradient inline-flex size-10 items-center justify-center rounded-xl text-white">
              <KeyRoundIcon className="size-5" aria-hidden />
            </span>
            <div>
              <h2 className="font-semibold">{provider.name}</h2>
              <p className="text-sm text-muted-foreground">{provider.blurb}</p>
            </div>
          </div>
          <StatusPill status={status} />
        </div>
        {status?.connected && status.checked_at && (
          <p className="text-xs text-muted-foreground">
            Last checked {formatDateTime(status.checked_at)}
          </p>
        )}
        {isAdmin && (editing || !status?.connected) && (
          <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex flex-1 flex-col gap-1.5">
              <Label htmlFor={`${id}-key`}>{provider.name} API key</Label>
              <Input
                id={`${id}-key`}
                type="password"
                autoComplete="off"
                value={key}
                onChange={(event) => setKey(event.target.value)}
                placeholder="Paste your key"
                minLength={8}
                required
              />
            </div>
            <Button type="submit" disabled={save.isPending || key.length < 8}>
              {save.isPending ? "Checking…" : "Save key"}
            </Button>
            {editing && (
              <Button type="button" variant="ghost" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            )}
          </form>
        )}
        {isAdmin && status?.connected && !editing && (
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={() => setEditing(true)}>
              Replace
            </Button>
            <Button
              variant="subtle"
              size="sm"
              onClick={() => test.mutate()}
              disabled={test.isPending}
            >
              {test.isPending ? "Testing…" : "Test"}
            </Button>
            <Button
              variant="destructive"
              size="sm"
              onClick={() => remove.mutate()}
              disabled={remove.isPending}
            >
              Remove
            </Button>
          </div>
        )}
        {error && (
          <p role="alert" className="text-sm text-destructive">
            {describe(error)}
          </p>
        )}
        <a
          href={provider.keysUrl}
          target="_blank"
          rel="noreferrer"
          className="inline-flex w-fit items-center gap-1 text-xs font-medium text-primary hover:underline"
        >
          Get a {provider.name} key <ExternalLinkIcon className="size-3" aria-hidden />
        </a>
      </section>
    </Panel>
  );
}
