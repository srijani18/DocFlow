import { activeParams, EMPTY_SEARCH, isSearching, snippetParts } from "./search";

describe("search helpers", () => {
  it("keeps only set, trimmed parameters and drops half-typed amounts", () => {
    expect(
      activeParams({ ...EMPTY_SEARCH, q: "  kaveri ", amount_min: "100.", amount_max: "2500" }),
    ).toEqual({ q: "kaveri", amount_max: "2500" });
    expect(isSearching(EMPTY_SEARCH)).toBe(false);
    expect(isSearching({ ...EMPTY_SEARCH, status: "APPROVED" })).toBe(true);
  });

  it("splits a snippet into matched and plain parts", () => {
    expect(snippetParts("[[Kaveri]] Fasteners [[Private]]")).toEqual([
      { text: "Kaveri", match: true },
      { text: " Fasteners ", match: false },
      { text: "Private", match: true },
    ]);
  });
});
