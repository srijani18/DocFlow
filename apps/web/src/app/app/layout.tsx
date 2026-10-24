import Link from "next/link";

import { SignOutButton } from "@/components/sign-out-button";

// proxy.ts has already sent signed-out visitors to /login before anything here renders.
export default function AppLayout({ children }: LayoutProps<"/app">) {
  return (
    <div className="flex flex-1 flex-col">
      <header className="border-b">
        <div className="mx-auto flex w-full max-w-3xl items-center justify-between px-6 py-3">
          <Link href="/app" className="font-semibold tracking-tight">
            DocFlow
          </Link>
          <SignOutButton />
        </div>
      </header>
      <main className="mx-auto flex w-full max-w-3xl flex-1 flex-col px-6 py-10">{children}</main>
    </div>
  );
}
