import { Suspense } from "react";

import { AppNav, NavLinks } from "@/components/app-nav";
import { Wordmark } from "@/components/brand";
import { SignOutButton } from "@/components/sign-out-button";

// proxy.ts has already sent signed-out visitors to /login before anything here renders.
export default function AppLayout({ children }: LayoutProps<"/app">) {
  return (
    <div className="flex min-h-svh flex-1 bg-surface">
      <aside className="sticky top-0 hidden h-svh w-64 shrink-0 flex-col border-r bg-sidebar px-4 py-6 md:flex">
        <div className="px-2">
          <Wordmark href="/app" />
        </div>
        <div className="mt-10 flex-1">
          <Suspense fallback={<NavLinks pathname={null} />}>
            <AppNav />
          </Suspense>
        </div>
        <SignOutButton />
      </aside>
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex items-center justify-between gap-3 border-b bg-white px-4 py-3 md:hidden">
          <Wordmark href="/app" size="sm" />
          <SignOutButton />
        </header>
        <div className="border-b bg-white px-2 py-1 md:hidden">
          <Suspense fallback={<NavLinks pathname={null} orientation="horizontal" />}>
            <AppNav orientation="horizontal" />
          </Suspense>
        </div>
        <main className="mx-auto flex w-full max-w-6xl flex-1 flex-col px-4 py-8 sm:px-8 sm:py-10">
          {children}
        </main>
      </div>
    </div>
  );
}
