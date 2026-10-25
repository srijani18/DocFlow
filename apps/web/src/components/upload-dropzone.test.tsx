import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ApiError } from "@/lib/api/transient";
import { uploadFile, type UploadOutcome } from "@/lib/upload";

import { UploadDropzone } from "./upload-dropzone";

vi.mock("@/lib/upload", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/upload")>()),
  uploadFile: vi.fn(),
}));
vi.mock("@/lib/supabase/browser", () => ({ getSupabaseBrowserClient: () => ({}) }));

const WS = "0f1e1a3c-6a43-4b6e-9a51-7d0c3c3b8a11";
const DOCUMENT = { id: "8a6e0804-2bd0-4672-b79d-d97027f9a0a1" } as UploadOutcome["document"];

function renderDropzone() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <UploadDropzone workspaceId={WS} />
    </QueryClientProvider>,
  );
}

function file(name: string, type = "application/pdf", size = 10) {
  return new File([new Uint8Array(size)], name, { type });
}

function drop(...files: File[]) {
  fireEvent.drop(screen.getByTestId("dropzone"), { dataTransfer: { files } });
}

function rowFor(name: string) {
  return within(screen.getByRole("list", { name: "Uploads" }))
    .getByText(name)
    .closest("li") as HTMLElement;
}

describe("UploadDropzone", () => {
  it("AC2: rejects large or wrong-type files before upload", () => {
    renderDropzone();

    drop(
      file("big.pdf", "application/pdf", 10 * 1024 * 1024 + 1),
      file("notes.docx", "application/msword"),
    );

    expect(rowFor("big.pdf")).toHaveTextContent("big.pdf is larger than 10 MB.");
    expect(rowFor("notes.docx")).toHaveTextContent("notes.docx isn't a PDF, PNG or JPEG.");
    expect(uploadFile).not.toHaveBeenCalled();
  });

  it("AC3: duplicate shows link to existing document", async () => {
    vi.mocked(uploadFile).mockResolvedValue({ kind: "duplicate", document: DOCUMENT });
    renderDropzone();

    await userEvent.upload(screen.getByLabelText("Choose files"), file("invoice.pdf"));

    expect(await within(rowFor("invoice.pdf")).findByText(/Already uploaded/)).toBeInTheDocument();
    expect(within(rowFor("invoice.pdf")).getByRole("link", { name: "View" })).toHaveAttribute(
      "href",
      `/app/documents/${DOCUMENT.id}`,
    );
  });

  it("AC6: one failing file doesn't stop the others", async () => {
    vi.mocked(uploadFile).mockImplementation(async (_ws, f) => {
      if (f.name === "bad.pdf") {
        throw new ApiError(409, {
          type: "x",
          title: "The file hasn't been uploaded",
          status: 409,
          detail: null,
          errors: null,
          request_id: null,
        });
      }
      return { kind: "created", document: DOCUMENT };
    });
    renderDropzone();

    drop(file("good-1.pdf"), file("bad.pdf"), file("good-2.png", "image/png"));

    expect(await within(rowFor("good-1.pdf")).findByText("Uploaded")).toBeInTheDocument();
    expect(await within(rowFor("good-2.png")).findByText("Uploaded")).toBeInTheDocument();
    expect(
      await within(rowFor("bad.pdf")).findByText("The file hasn't been uploaded"),
    ).toBeInTheDocument();
    expect(uploadFile).toHaveBeenCalledTimes(3);
  });

  it("AC7: shows the synthetic-data notice", () => {
    renderDropzone();

    expect(screen.getByText(/Upload only sample or synthetic documents/)).toBeInTheDocument();
  });
});
