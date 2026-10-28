"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BotIcon, CheckIcon, CopyIcon } from "lucide-react";
import { useState, type FormEvent } from "react";

import { MeGate } from "@/components/me-gate";
import { Panel } from "@/components/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { env } from "@/env";
import {
  apiTokenKeys,
  createApiToken,
  fetchApiTokens,
  revokeApiToken,
  type ApiToken,
  type ApiTokenCreated,
  type ExpiryDays,
} from "@/lib/api/api-tokens";
import { currentWorkspace } from "@/lib/api/me";
import { ApiError, problemMessage } from "@/lib/api/transient";
import { formatDateTime } from "@/lib/format";

const EXPIRY_OPTIONS: { days: ExpiryDays; label: string }[] = [
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
  { days: 365, label: "1 year" },
];

export const MCP_URL = `${env.NEXT_PUBLIC_API_BASE_URL.replace(/\/$/, "")}/mcp`;

export function AssistantAccessView() {
  return (
    <MeGate>
      {(me) => {
        const membership = currentWorkspace(me);
        if (membership === undefined) return null;
        return (
          <AssistantAccess
            workspaceId={membership.workspace.id}
            isAdmin={membership.role === "admin"}
          />
        );
      }}
    </MeGate>
  );
}

/** Ready-to-paste client configuration for a new token (F12 AC1). */
export function clientSnippets(token: string): { label: string; text: string }[] {
  return [
    {
      label: "Claude Code",
      text: `claude mcp add --transport http docflow ${MCP_URL} --header "Authorization: Bearer ${token}"`,
    },
    {
      label: "Claude Desktop (claude_desktop_config.json)",
      text: JSON.stringify(
        {
          mcpServers: {
            docflow: {
              command: "npx",
              args: ["-y", "mcp-remote", MCP_URL, "--header", "Authorization:${AUTH_HEADER}"],
              env: { AUTH_HEADER: `Bearer ${token}` },
            },
          },
        },
        null,
        2,
      ),
    },
  ];
}

function describe(error: unknown): string {
  if (error instanceof ApiError) return problemMessage(error, "Something went wrong.");
  return "Couldn't reach DocFlow. Try again.";
}

function tokenState(token: ApiToken): string {
  if (token.revoked_at) return "Revoked";
  if (new Date(token.expires_at) <= new Date()) return "Expired";
  return token.active ? "Active" : "Inactive";
}

/** Access tokens for AI assistants (F12). Members manage their own; admins see all. */
export function AssistantAccess({
  workspaceId,
  isAdmin,
}: {
  workspaceId: string;
  isAdmin: boolean;
}) {
  const queryClient = useQueryClient();
  const [name, setName] = useState("");
  const [days, setDays] = useState<ExpiryDays>(90);
  const [created, setCreated] = useState<ApiTokenCreated | null>(null);
  const tokens = useQuery({
    queryKey: apiTokenKeys.list(workspaceId),
    queryFn: () => fetchApiTokens(workspaceId),
  });
  const refresh = () => queryClient.invalidateQueries({ queryKey: apiTokenKeys.list(workspaceId) });
  const create = useMutation({
    mutationFn: () => createApiToken(workspaceId, name.trim(), days),
    onSuccess: (token) => {
      setCreated(token);
      setName("");
      void refresh();
    },
  });

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    create.mutate();
  }

  return (
    <Panel>
      <section aria-label="AI assistants (MCP)" className="flex flex-col gap-5">
        <div className="flex items-center gap-3">
          <span className="bg-brand-gradient inline-flex size-10 items-center justify-center rounded-xl text-white">
            <BotIcon className="size-5" aria-hidden />
          </span>
          <div>
            <h2 className="font-semibold">AI assistants (MCP)</h2>
            <p className="text-sm text-muted-foreground">
              Let Claude, Cursor or another MCP client search your documents and add up spend. A
              token can only read, acts as you in this workspace, and sends the data it reads to
              your assistant.
            </p>
          </div>
        </div>

        {created ? (
          <NewToken token={created} onDone={() => setCreated(null)} />
        ) : (
          <form onSubmit={onSubmit} className="flex flex-col gap-2 sm:flex-row sm:items-end">
            <div className="flex flex-1 flex-col gap-1.5">
              <Label htmlFor="token-name">Token name</Label>
              <Input
                id="token-name"
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="e.g. Claude on my laptop"
                maxLength={80}
                required
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="token-expiry">Expires after</Label>
              <select
                id="token-expiry"
                value={days}
                onChange={(event) => setDays(Number(event.target.value) as ExpiryDays)}
                className="h-9 rounded-md border bg-background px-3 text-sm"
              >
                {EXPIRY_OPTIONS.map((option) => (
                  <option key={option.days} value={option.days}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>
            <Button type="submit" disabled={create.isPending || name.trim() === ""}>
              {create.isPending ? "Creating…" : "Create token"}
            </Button>
          </form>
        )}
        {create.isError && (
          <p role="alert" className="text-sm text-destructive">
            {describe(create.error)}
          </p>
        )}

        {tokens.isPending ? (
          <p className="text-sm text-muted-foreground">Loading…</p>
        ) : tokens.isError ? (
          <p role="alert" className="text-sm text-destructive">
            Couldn&apos;t load tokens.
          </p>
        ) : tokens.data.length === 0 ? (
          <p className="text-sm text-muted-foreground">No tokens yet.</p>
        ) : (
          <TokenTable
            workspaceId={workspaceId}
            tokens={tokens.data}
            isAdmin={isAdmin}
            onChange={refresh}
          />
        )}
      </section>
    </Panel>
  );
}

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <Button
      type="button"
      variant="outline"
      size="sm"
      onClick={() => {
        void navigator.clipboard.writeText(text).then(() => setCopied(true));
      }}
    >
      {copied ? <CheckIcon aria-hidden /> : <CopyIcon aria-hidden />}
      {copied ? "Copied" : label}
    </Button>
  );
}

function NewToken({ token, onDone }: { token: ApiTokenCreated; onDone: () => void }) {
  return (
    <div className="flex flex-col gap-4 rounded-2xl border border-amber-300 bg-amber-50/60 p-4 dark:border-amber-800 dark:bg-amber-950/30">
      <p className="text-sm font-medium">
        Copy your token now. You won&apos;t be able to see it again.
      </p>
      <div className="flex flex-wrap items-center gap-2">
        <code
          aria-label="New token"
          className="min-w-0 flex-1 rounded-lg bg-background px-3 py-2 font-mono text-xs break-all"
        >
          {token.token}
        </code>
        <CopyButton text={token.token} label="Copy token" />
      </div>
      {clientSnippets(token.token).map((snippet) => (
        <div key={snippet.label} className="flex flex-col gap-1.5">
          <div className="flex items-center justify-between gap-2">
            <span className="text-xs font-medium text-muted-foreground">{snippet.label}</span>
            <CopyButton text={snippet.text} label="Copy" />
          </div>
          <pre className="overflow-x-auto rounded-lg bg-background p-3 font-mono text-xs">
            {snippet.text}
          </pre>
        </div>
      ))}
      <Button type="button" onClick={onDone} className="w-fit">
        Done
      </Button>
    </div>
  );
}

function TokenTable({
  workspaceId,
  tokens,
  isAdmin,
  onChange,
}: {
  workspaceId: string;
  tokens: ApiToken[];
  isAdmin: boolean;
  onChange: () => void;
}) {
  const [confirming, setConfirming] = useState<string | null>(null);
  const revoke = useMutation({
    mutationFn: (tokenId: string) => revokeApiToken(workspaceId, tokenId),
    onSuccess: () => {
      setConfirming(null);
      onChange();
    },
  });
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="text-left text-muted-foreground">
          <tr>
            <th scope="col" className="py-2 pr-4 font-normal">
              Name
            </th>
            {isAdmin && (
              <th scope="col" className="py-2 pr-4 font-normal">
                Created by
              </th>
            )}
            <th scope="col" className="py-2 pr-4 font-normal">
              Last used
            </th>
            <th scope="col" className="py-2 pr-4 font-normal">
              Expires
            </th>
            <th scope="col" className="py-2 pr-4 font-normal">
              Status
            </th>
            <th scope="col" className="py-2 font-normal">
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y">
          {tokens.map((token) => {
            const state = tokenState(token);
            return (
              <tr key={token.id}>
                <th scope="row" className="py-2 pr-4 text-left font-medium">
                  {token.name}{" "}
                  <span className="font-mono text-xs font-normal text-muted-foreground">
                    {token.prefix}…
                  </span>
                </th>
                {isAdmin && <td className="py-2 pr-4">{token.created_by ?? "—"}</td>}
                <td className="py-2 pr-4">
                  {token.last_used_at ? formatDateTime(token.last_used_at) : "Never"}
                </td>
                <td className="py-2 pr-4">{formatDateTime(token.expires_at)}</td>
                <td className="py-2 pr-4">{state}</td>
                <td className="py-2 text-right">
                  {state === "Active" &&
                    (confirming === token.id ? (
                      <Button
                        variant="destructive"
                        size="sm"
                        disabled={revoke.isPending}
                        onClick={() => revoke.mutate(token.id)}
                      >
                        Confirm revoke
                      </Button>
                    ) : (
                      <Button variant="outline" size="sm" onClick={() => setConfirming(token.id)}>
                        Revoke
                      </Button>
                    ))}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {revoke.isError && (
        <p role="alert" className="mt-2 text-sm text-destructive">
          {describe(revoke.error)}
        </p>
      )}
    </div>
  );
}
