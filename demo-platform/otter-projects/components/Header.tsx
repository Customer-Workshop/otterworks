"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

export default function Header({ crumbs = [] }: { crumbs?: { label: string; href?: string }[] }) {
  const router = useRouter();
  async function logout() {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      router.replace("/login");
    }
  }
  return (
    <header className="flex items-center justify-between border-b border-slate-200 bg-white px-5 py-3">
      <nav className="flex items-center gap-2 text-sm">
        <Link href="/" className="flex items-center gap-2 font-semibold text-slate-900">
          <span className="inline-block h-6 w-6 rounded bg-slate-900 text-center text-xs leading-6 text-white">OP</span>
          Otter Projects
        </Link>
        {crumbs.map((c) => (
          <span key={c.label} className="flex items-center gap-2 text-slate-500">
            <span>/</span>
            {c.href ? (
              <Link href={c.href} className="hover:text-slate-900">
                {c.label}
              </Link>
            ) : (
              <span className="text-slate-900">{c.label}</span>
            )}
          </span>
        ))}
      </nav>
      <button type="button" onClick={logout} className="btn-xs">
        Sign out
      </button>
    </header>
  );
}
