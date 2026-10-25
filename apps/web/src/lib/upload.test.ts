import { createSupabaseMock, sessionWithToken } from "@/test/supabase-mock";

import { MAX_UPLOAD_BYTES, uploadFile, validateFile } from "./upload";

const supabase = createSupabaseMock();
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => supabase.client }));

const WS = "0f1e1a3c-6a43-4b6e-9a51-7d0c3c3b8a11";
const DOCUMENT = {
  id: "8a6e0804-2bd0-4672-b79d-d97027f9a0a1",
  filename: "invoice.pdf",
  content_type: "application/pdf",
  size_bytes: 9,
  sha256: "x",
  status: "UPLOADED",
  failure_reason: null,
  created_at: "2026-10-25T10:00:00Z",
  updated_at: "2026-10-25T10:00:00Z",
};
const TICKET = {
  kind: "upload",
  upload_id: "11111111-1111-1111-1111-111111111111",
  bucket: "documents-dev",
  path: `${WS}/11111111-1111-1111-1111-111111111111`,
  token: "signed-token",
  expires_at: "2026-10-25T12:00:00Z",
};

function pdf(name = "invoice.pdf", content = "%PDF-1.7") {
  return new File([content], name, { type: "application/pdf" });
}

beforeEach(() => {
  supabase.auth.getSession.mockResolvedValue({
    data: { session: sessionWithToken("t") },
    error: null,
  });
});

describe("validateFile", () => {
  it("AC2: rejects files over 10 MB", () => {
    const big = new File([new Uint8Array(MAX_UPLOAD_BYTES + 1)], "big.pdf", {
      type: "application/pdf",
    });
    expect(validateFile(big)).toBe("big.pdf is larger than 10 MB.");
  });

  it("AC2: rejects other types and empty files", () => {
    expect(validateFile(new File(["x"], "a.docx", { type: "application/msword" }))).toBe(
      "a.docx isn't a PDF, PNG or JPEG.",
    );
    expect(validateFile(new File([], "empty.pdf", { type: "application/pdf" }))).toBe(
      "empty.pdf is empty.",
    );
  });

  it("accepts PDF, PNG and JPEG up to 10 MB", () => {
    expect(validateFile(pdf())).toBeNull();
    expect(validateFile(new File(["x"], "r.png", { type: "image/png" }))).toBeNull();
    expect(validateFile(new File(["x"], "r.jpg", { type: "image/jpeg" }))).toBeNull();
  });
});

describe("uploadFile", () => {
  it("AC1: hashes, uploads to the signed URL, then completes", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json(TICKET, { status: 201 }))
      .mockResolvedValueOnce(Response.json(DOCUMENT, { status: 201 }));
    const phases: string[] = [];

    const outcome = await uploadFile(WS, pdf(), (phase) => phases.push(phase));

    expect(outcome).toEqual({ kind: "created", document: DOCUMENT });
    const start = fetchMock.mock.calls[0]?.[0] as Request;
    expect(await start.json()).toEqual({
      filename: "invoice.pdf",
      content_type: "application/pdf",
      size_bytes: 8,
      sha256: "86edbaa24831badfa0a8b04bb410141e2ee4182b6d0014493fe262a7a331c20b", // sha256 of "%PDF-1.7"
    });
    expect(supabase.storage.from).toHaveBeenCalledWith("documents-dev");
    expect(supabase.uploadToSignedUrl).toHaveBeenCalledWith(
      TICKET.path,
      "signed-token",
      expect.any(File),
      {
        contentType: "application/pdf",
      },
    );
    const done = fetchMock.mock.calls[1]?.[0] as Request;
    expect(done.url).toBe(
      `http://api.test/v1/workspaces/${WS}/uploads/${TICKET.upload_id}/complete`,
    );
    expect(phases).toEqual(["hashing", "uploading", "finishing"]);
  });

  it("AC3: a duplicate skips the upload and returns the existing document", async () => {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce(
      Response.json({ kind: "duplicate", document: DOCUMENT }, { status: 200 }),
    );

    const outcome = await uploadFile(WS, pdf());

    expect(outcome).toEqual({ kind: "duplicate", document: DOCUMENT });
    expect(supabase.uploadToSignedUrl).not.toHaveBeenCalled();
  });

  it("fails with the storage error and doesn't complete", async () => {
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValueOnce(Response.json(TICKET, { status: 201 }));
    supabase.uploadToSignedUrl.mockResolvedValueOnce({
      data: null,
      error: new Error("mime type not allowed"),
    });

    await expect(uploadFile(WS, pdf())).rejects.toThrow("The file couldn't be uploaded");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
