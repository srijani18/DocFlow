import type { Metadata } from "next";

import { DocumentsView } from "./documents-view";

export const metadata: Metadata = { title: "Documents · DocFlow" };

export default function DocumentsPage() {
  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
      <DocumentsView />
    </section>
  );
}
