import type { Metadata } from "next";

import { PageHeader } from "@/components/page-header";

import { AiKeysView } from "./ai-keys-view";
import { AssistantAccessView } from "./assistant-access";

export const metadata: Metadata = { title: "Settings · DocFlow" };

export default function SettingsPage() {
  return (
    <section className="flex flex-col gap-8">
      <PageHeader
        title="Settings"
        description="Your AI provider keys, and access for your AI assistants."
      />
      <AiKeysView />
      <AssistantAccessView />
    </section>
  );
}
