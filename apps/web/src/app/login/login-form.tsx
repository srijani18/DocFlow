"use client";

import {
  isAuthRetryableFetchError,
  isAuthWeakPasswordError,
  type AuthError,
} from "@supabase/supabase-js";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, type FormEvent } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { safeNext } from "@/lib/safe-next";
import { getSupabaseBrowserClient } from "@/lib/supabase/browser";

type Mode = "sign-in" | "sign-up";

// Matches the minimum set in the Supabase dashboard (F1 plan §8). Supabase enforces it;
// this only lets the browser say so before a round trip.
const MIN_PASSWORD_LENGTH = 10;

const SUBMIT_LABEL: Record<Mode, string> = { "sign-in": "Sign in", "sign-up": "Create account" };

/**
 * What to show for a failed sign-in or sign-up. Account problems get one generic message
 * per mode, so the page never reveals whether an email address has an account (spec AC2).
 */
function errorMessage(mode: Mode, error: AuthError): string {
  if (isAuthRetryableFetchError(error)) {
    return "Couldn't reach the sign-in service. Check your connection and try again.";
  }
  if (error.status === 429) {
    return "Too many attempts. Wait a minute and try again.";
  }
  if (mode === "sign-up" && isAuthWeakPasswordError(error)) {
    return error.message;
  }
  return mode === "sign-in"
    ? "Incorrect email or password."
    : "Couldn't create an account with those details. If you already have one, sign in instead.";
}

function AuthForm({ mode, onAccountCreated }: { mode: Mode; onAccountCreated: () => void }) {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    const credentials = {
      email: String(form.get("email") ?? "").trim(),
      password: String(form.get("password") ?? ""),
    };
    setPending(true);
    setError(null);

    const auth = getSupabaseBrowserClient().auth;
    const { data, error } =
      mode === "sign-in"
        ? await auth.signInWithPassword(credentials)
        : await auth.signUp(credentials);

    if (error !== null) {
      setError(errorMessage(mode, error));
      setPending(false);
      return;
    }
    if (data.session === null) {
      // Only happens if email confirmation gets switched on in Supabase (spec Q1 keeps it off).
      setPending(false);
      onAccountCreated();
      return;
    }
    // Keep the button disabled while the app loads.
    router.replace(next);
  }

  const idPrefix = `${mode}-`;
  return (
    <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${idPrefix}email`}>Email</Label>
        <Input id={`${idPrefix}email`} name="email" type="email" autoComplete="email" required />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor={`${idPrefix}password`}>Password</Label>
        <Input
          id={`${idPrefix}password`}
          name="password"
          type="password"
          autoComplete={mode === "sign-in" ? "current-password" : "new-password"}
          minLength={mode === "sign-up" ? MIN_PASSWORD_LENGTH : undefined}
          aria-describedby={mode === "sign-up" ? `${idPrefix}password-hint` : undefined}
          required
        />
        {mode === "sign-up" && (
          <p id={`${idPrefix}password-hint`} className="text-xs text-muted-foreground">
            At least {MIN_PASSWORD_LENGTH} characters.
          </p>
        )}
      </div>
      {error !== null && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <Button type="submit" size="lg" disabled={pending}>
        {SUBMIT_LABEL[mode]}
      </Button>
    </form>
  );
}

export function LoginForm() {
  const [mode, setMode] = useState<Mode>("sign-in");
  const [notice, setNotice] = useState<string | null>(null);

  return (
    <Card className="w-full rounded-3xl border shadow-xl shadow-primary/5">
      <CardHeader>
        <CardTitle className="text-lg">Sign in or create an account</CardTitle>
        <CardDescription>New accounts get their own workspace.</CardDescription>
      </CardHeader>
      <CardContent>
        <Tabs value={mode} onValueChange={(value: Mode) => setMode(value)}>
          <TabsList className="w-full rounded-full">
            <TabsTrigger value="sign-in">Sign in</TabsTrigger>
            <TabsTrigger value="sign-up">Create account</TabsTrigger>
          </TabsList>
          {notice !== null && (
            <p role="status" className="text-sm text-muted-foreground">
              {notice}
            </p>
          )}
          <TabsContent value="sign-in">
            <AuthForm mode="sign-in" onAccountCreated={() => undefined} />
          </TabsContent>
          <TabsContent value="sign-up">
            <AuthForm
              mode="sign-up"
              onAccountCreated={() => {
                setNotice("Account created. Sign in to continue.");
                setMode("sign-in");
              }}
            />
          </TabsContent>
        </Tabs>
      </CardContent>
    </Card>
  );
}
