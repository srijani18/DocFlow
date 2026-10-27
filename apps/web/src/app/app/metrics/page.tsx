import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";

import { MetricsView } from "./metrics-view";

export const metadata: Metadata = { title: "Metrics · DocFlow" };

export default function MetricsPage() {
  return (
    <section className="flex flex-col gap-8">
      <PageHeader
        title="Metrics"
        description="How DocFlow is doing on your workspace's documents."
      />
      <MetricsView />
    </section>
  );
}
