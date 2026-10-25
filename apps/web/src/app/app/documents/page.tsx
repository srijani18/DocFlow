import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";

import { DocumentsView } from "./documents-view";

export const metadata: Metadata = { title: "Documents · DocFlow" };

export default function DocumentsPage() {
  return (
    <section className="flex flex-col gap-8">
      <PageHeader
        title="Documents"
        description="Upload invoices, receipts and purchase orders. Statuses update live."
      />
      <DocumentsView />
    </section>
  );
}
