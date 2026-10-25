import type { Metadata } from "next";
import Link from "next/link";
import { Suspense } from "react";

import { DocumentDetailView } from "./document-detail";

export const metadata: Metadata = { title: "Document · DocFlow" };

export default function DocumentPage() {
  return (
    <section className="flex flex-col gap-6">
      <Link href="/app/documents" className="text-sm text-muted-foreground hover:underline">
        ← Documents
      </Link>
      {/* The document id comes from the URL, which is only known at request time. */}
      <Suspense>
        <DocumentDetailView />
      </Suspense>
    </section>
  );
}
