import type { Metadata } from "next";
import { Suspense } from "react";

import { LoginForm } from "./login-form";

export const metadata: Metadata = { title: "Sign in · DocFlow" };

export default function LoginPage() {
  return (
    <main className="flex flex-1 items-center justify-center px-6 py-24">
      {/* The form reads ?next= from the URL, which is only known at request time. */}
      <Suspense>
        <LoginForm />
      </Suspense>
    </main>
  );
}
