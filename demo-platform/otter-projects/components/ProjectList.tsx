"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import Header from "@/components/Header";
import { apiGet, apiSend } from "@/lib/client";
import type { Project } from "@/lib/types";

export default function ProjectList() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ key: "", name: "", repo: "", description: "" });

  const load = useCallback(async () => {
    try {
      const data = await apiGet<{ projects: Project[] }>("/api/projects");
      setProjects(data.projects);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "failed to load");
      setProjects([]);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    try {
      await apiSend("/api/projects", "POST", form);
      setForm({ key: "", name: "", repo: "", description: "" });
      setCreating(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "failed to create");
    }
  }

  return (
    <div className="min-h-screen">
      <Header />
      <main className="mx-auto max-w-4xl px-5 py-8">
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-semibold">Projects</h1>
          <button type="button" className="btn-primary" onClick={() => setCreating((v) => !v)}>
            {creating ? "Cancel" : "New project"}
          </button>
        </div>
        {error && (
          <div role="alert" className="mt-4 flex items-center justify-between rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
            {error}
            <button type="button" className="btn-xs" onClick={() => setError(null)}>
              Dismiss
            </button>
          </div>
        )}
        {creating && (
          <form onSubmit={create} className="mt-4 grid gap-3 rounded-xl border border-slate-200 bg-white p-4 sm:grid-cols-2">
            <label className="text-sm">
              Key
              <input className="input mt-1 uppercase" required value={form.key} onChange={(e) => setForm({ ...form, key: e.target.value.toUpperCase() })} placeholder="OTTER" />
            </label>
            <label className="text-sm">
              Name
              <input className="input mt-1" required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} />
            </label>
            <label className="text-sm sm:col-span-2">
              Repository
              <input className="input mt-1" value={form.repo} onChange={(e) => setForm({ ...form, repo: e.target.value })} placeholder="org/repo" />
            </label>
            <label className="text-sm sm:col-span-2">
              Description
              <textarea className="input mt-1" rows={2} value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
            </label>
            <div className="sm:col-span-2">
              <button type="submit" className="btn-primary">
                Create project
              </button>
            </div>
          </form>
        )}
        {projects === null ? (
          <p className="mt-6 text-sm text-slate-500">Loading…</p>
        ) : projects.length === 0 ? (
          <p className="mt-6 text-sm text-slate-500">No projects yet. Create one or run <code>npm run seed</code>.</p>
        ) : (
          <ul className="mt-6 grid gap-3 sm:grid-cols-2">
            {projects.map((p) => (
              <li key={p.key}>
                <Link href={`/projects/${p.key}`} className="block rounded-xl border border-slate-200 bg-white p-4 shadow-sm hover:border-slate-400">
                  <div className="flex items-center gap-2">
                    <span className="chip bg-slate-900 text-white">{p.key}</span>
                    <span className="font-medium">{p.name}</span>
                  </div>
                  {p.description && <p className="mt-2 line-clamp-2 text-sm text-slate-600">{p.description}</p>}
                  <p className="mt-2 text-xs text-slate-500">
                    {p.repo || "no repo"} · dispatcher: {p.dispatcher}
                  </p>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </main>
    </div>
  );
}
