import { WORKSPACE_ID } from "@/test/fixtures";

import { followEvents, parseEvents, reconnectDelay, type DocumentStatusEvent } from "./events";

const STATUS: DocumentStatusEvent = {
  document_id: "8a6e0804-2bd0-4672-b79d-d97027f9a0a1",
  status: "NEEDS_REVIEW",
  failure_reason: null,
  changed_at: "2026-10-25T10:00:00Z",
};

function sseResponse(...chunks: string[]) {
  const encoder = new TextEncoder();
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
      controller.close();
    },
  });
  return new Response(body, { headers: { "Content-Type": "text/event-stream" } });
}

describe("parseEvents", () => {
  it("splits complete events, skips comments and keeps the remainder", () => {
    const { events, rest } = parseEvents(
      'event: ready\ndata: {}\n\n: keep-alive\n\nevent: document.status\ndata: {"a":1}\n\nevent: docu',
    );

    expect(events).toEqual([
      { event: "ready", data: "{}" },
      { event: "document.status", data: '{"a":1}' },
    ]);
    expect(rest).toBe("event: docu");
  });
});

describe("reconnectDelay", () => {
  it("backs off from 1 s to 30 s", () => {
    expect([1, 2, 3, 6, 10].map(reconnectDelay)).toEqual([1000, 2000, 4000, 30_000, 30_000]);
  });
});

describe("followEvents", () => {
  it("AC9: dispatches ready and status events, with the Bearer token", async () => {
    const controller = new AbortController();
    const onStatus = vi.fn(() => controller.abort());
    const onReady = vi.fn();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      // An event split across two network chunks still arrives whole.
      .mockResolvedValueOnce(
        sseResponse(
          "event: ready\ndata: {}\n\n",
          "event: document.status\ndata: ",
          `${JSON.stringify(STATUS)}\n\n`,
        ),
      );

    await followEvents(WORKSPACE_ID, { onReady, onStatus }, controller.signal, async () => "tok");

    expect(onReady).toHaveBeenCalledTimes(1);
    expect(onStatus).toHaveBeenCalledWith(STATUS);
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toBe(`http://api.test/v1/workspaces/${WORKSPACE_ID}/events`);
    expect(new Headers(init.headers).get("Authorization")).toBe("Bearer tok");
  });

  it("AC9: reconnects after the stream drops", async () => {
    vi.useFakeTimers();
    try {
      const controller = new AbortController();
      let readies = 0;
      const onReady = () => {
        readies += 1;
        if (readies === 2) controller.abort();
      };
      const fetchMock = vi
        .spyOn(globalThis, "fetch")
        .mockRejectedValueOnce(new TypeError("Failed to fetch")) // server waking up
        .mockResolvedValueOnce(sseResponse("event: ready\ndata: {}\n\n")) // then drops
        .mockResolvedValueOnce(sseResponse("event: ready\ndata: {}\n\n"));

      const done = followEvents(
        WORKSPACE_ID,
        { onReady, onStatus: vi.fn() },
        controller.signal,
        async () => null,
      );
      await vi.advanceTimersByTimeAsync(5_000);
      await done;

      expect(readies).toBe(2);
      expect(fetchMock).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });
});
