import { APP_HOME, loginPath, safeNext } from "./safe-next";

describe("safeNext", () => {
  it.each([
    ["/app", "/app"],
    ["/app/", "/app/"],
    ["/app/documents/42", "/app/documents/42"],
    ["/app/documents?status=review#top", "/app/documents?status=review#top"],
    ["/app?tab=1", "/app?tab=1"],
  ])("AC3: only /app relative paths are allowed as next (keeps %s)", (next, expected) => {
    expect(safeNext(next)).toBe(expected);
  });

  it.each([
    [null],
    [undefined],
    [""],
    ["app"],
    ["/"],
    ["/login"],
    ["/application"],
    ["/apple/app"],
    ["https://evil.example/app"],
    ["//evil.example/app"],
    ["/\\evil.example/app"],
    ["\\\\evil.example/app"],
    ["/app/../admin"],
    ["/app/%2e%2e/admin"],
    ["javascript:alert(1)//app"],
    [" /app"],
    ["/app\n//evil.example"],
  ])("AC3: only /app relative paths are allowed as next (rejects %j)", (next) => {
    expect(safeNext(next)).toBe(APP_HOME);
  });
});

describe("loginPath", () => {
  it("carries the requested app page as next", () => {
    expect(loginPath("/app/documents?status=review")).toBe(
      "/login?next=%2Fapp%2Fdocuments%3Fstatus%3Dreview",
    );
  });

  it("drops next when it would be the app home anyway", () => {
    expect(loginPath("/app")).toBe("/login");
    expect(loginPath("https://evil.example")).toBe("/login");
  });
});
