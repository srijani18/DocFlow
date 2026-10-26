import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";

import { AiKeysView } from "./ai-keys-view";

export const metadata: Metadata = { title: "Settings · DocFlow" };

export default function SettingsPage() {
  return (
    <section className="flex flex-col gap-8">
      <PageHeader title="Settings" description="Connect your own AI provider keys." />
      <AiKeysView />
    </section>
  );
}
