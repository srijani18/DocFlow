import type { components } from "@/generated/api";
import { env } from "@/env";

export type DocumentStatus = components["schemas"]["DocumentStatus"];

/** `data` of a `document.status` event; mirrors DocumentStatusEvent in app/documents/schemas.py. */
export type DocumentStatusEvent = {
  document_id: string;
  status: DocumentStatus;
  failure_reason: string | null;
  changed_at: string;
};

export type EventHandlers = {
  /** Sent on every (re)connect: refetch, since events may have been missed meanwhile. */
  onReady: () => void;
  onStatus: (event: DocumentStatusEvent) => void;
};

type ServerSentEvent = { event: string; data: string };

/** Splits complete events off the front of a text/event-stream buffer. */
export function parseEvents(buffer: string): { events: ServerSentEvent[]; rest: string } {
  const blocks = buffer.split("\n\n");
  const rest = blocks.pop() ?? "";
  const events: ServerSentEvent[] = [];
  for (const block of blocks) {
    let event = "message";
    const data: string[] = [];
    for (const line of block.split("\n")) {
      if (line.startsWith(":")) continue; // comment, e.g. keep-alive
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (data.length > 0) events.push({ event, data: data.join("\n") });
  }
  return { events, rest };
}

/** Wait before reconnect number `attempt` (1-based): 1 s, 2 s, 4 s… up to 30 s. */
export function reconnectDelay(attempt: number): number {
  return Math.min(1000 * 2 ** (attempt - 1), 30_000);
}

function sleep(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    const timer = setTimeout(resolve, ms);
    signal.addEventListener("abort", () => {
      clearTimeout(timer);
      resolve();
    });
  });
}

/**
 * Follows a workspace's live status stream until `signal` aborts (F3 AC9), reconnecting
 * with backoff when it drops. Uses fetch rather than EventSource, because EventSource
 * can't send the Bearer token.
 */
export async function followEvents(
  workspaceId: string,
  handlers: EventHandlers,
  signal: AbortSignal,
  accessToken: () => Promise<string | null>,
): Promise<void> {
  const url = `${env.NEXT_PUBLIC_API_BASE_URL}/v1/workspaces/${workspaceId}/events`;
  let failures = 0;
  while (!signal.aborted) {
    try {
      const token = await accessToken();
      const response = await globalThis.fetch(url, {
        headers: token ? { Authorization: `Bearer ${token}`, Accept: "text/event-stream" } : {},
        cache: "no-store",
        signal,
      });
      if (!response.ok || response.body === null) {
        throw new Error(`event stream failed with ${response.status}`);
      }
      failures = 0;
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";
      for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const parsed = parseEvents(buffer);
        buffer = parsed.rest;
        for (const { event, data } of parsed.events) {
          if (event === "ready") handlers.onReady();
          if (event === "document.status")
            handlers.onStatus(JSON.parse(data) as DocumentStatusEvent);
        }
      }
      // The server closes streams after 30 minutes; reconnect promptly.
    } catch {
      if (signal.aborted) return;
      failures += 1;
    }
    await sleep(failures === 0 ? 0 : reconnectDelay(failures), signal);
  }
}
