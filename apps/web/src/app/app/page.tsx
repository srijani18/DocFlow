import type { Metadata } from "next";

import { HomeView } from "./home-view";

export const metadata: Metadata = { title: "Home · DocFlow" };

export default function AppHomePage() {
  return (
    <section className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Home</h1>
      <HomeView />
    </section>
  );
}
