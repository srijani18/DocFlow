import Link from "next/link";

import { ApiStatus } from "@/components/api-status";
import { buttonVariants } from "@/components/ui/button";

export default function Home() {
  return (
    <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col justify-center gap-4 px-6 py-24">
      <h1 className="text-4xl font-semibold tracking-tight">DocFlow</h1>
      <p className="text-lg text-muted-foreground">
        Upload invoices, receipts and purchase orders. DocFlow extracts, validates and routes them
        for review.
      </p>
      <div>
        <Link href="/app" className={buttonVariants({ size: "lg" })}>
          Sign in
        </Link>
      </div>
      <ApiStatus />
    </main>
  );
}
