/** Mocks fetch by URL path, so components that make several requests get the right answers. */
export function routeFetch(routes: Record<string, () => Response>) {
  return vi.spyOn(globalThis, "fetch").mockImplementation(async (input) => {
    const url = new URL(input instanceof Request ? input.url : String(input));
    for (const [suffix, respond] of Object.entries(routes)) {
      if (url.pathname.endsWith(suffix)) return respond();
    }
    return new Response("not mocked", { status: 599 });
  });
}
