"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";

export default function LoginPage() {
  const router = useRouter();
  const [passcode, setPasscode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ passcode }),
      });
      if (res.ok) {
        router.replace("/");
        router.refresh();
        return;
      }
      if (res.status === 429) {
        const retry = res.headers.get("Retry-After");
        setError(`Too many attempts. Try again in ${retry ?? "a few"}s.`);
      } else {
        setError("Invalid passcode.");
      }
    } catch {
      setError("Network error.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center px-4">
      <form
        onSubmit={onSubmit}
        className="w-full max-w-sm rounded-xl border border-slate-200 bg-white p-8 shadow-sm"
      >
        <h1 className="text-xl font-semibold">OtterWorks Demo Ops</h1>
        <p className="mt-1 text-sm text-slate-500">Enter the facilitator passcode.</p>

        <label htmlFor="passcode" className="mt-6 block text-sm font-medium">
          Passcode
        </label>
        <input
          id="passcode"
          type="password"
          autoComplete="off"
          autoFocus
          value={passcode}
          onChange={(e) => setPasscode(e.target.value)}
          className="mt-1 w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-slate-500 focus:outline-none"
        />

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={busy || passcode.length === 0}
          className="mt-6 w-full rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
        >
          {busy ? "Signing in…" : "Sign in"}
        </button>
      </form>
    </main>
  );
}
