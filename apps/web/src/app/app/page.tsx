import type { Metadata } from "next";

import { HomeView } from "./home-view";

export const metadata: Metadata = { title: "Dashboard · DocFlow" };

export default function AppHomePage() {
  return <HomeView />;
}
