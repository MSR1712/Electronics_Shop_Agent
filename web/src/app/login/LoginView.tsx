"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { adminApi, adminErrorMessage, api, ApiError } from "@/lib/api";
import type { Customer } from "@/lib/types";
import { useSession } from "@/context/SessionContext";

type Tab = "login" | "signup" | "admin";

const TABS: { id: Tab; label: string }[] = [
  { id: "login", label: "Log in" },
  { id: "signup", label: "Sign up" },
  { id: "admin", label: "Admin" },
];

export default function LoginView() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const redirect = searchParams.get("redirect") || "/";
  const { login, signup, loginDemo } = useSession();

  const [tab, setTab] = useState<Tab>("login");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [customers, setCustomers] = useState<Customer[]>([]);
  const [showDemo, setShowDemo] = useState(false);
  const [demoBusyId, setDemoBusyId] = useState<string | null>(null);

  useEffect(() => {
    api.listCustomers().then(setCustomers);
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    if (tab === "admin") {
      // Separate cw_admin cookie (api/admin_session.py) — doesn't touch the
      // customer session, and app/admin/layout.tsx picks it up on load.
      try {
        await adminApi.login(password);
        router.push("/admin");
      } catch (err) {
        setError(adminErrorMessage(err, "Could not log in as admin."));
      } finally {
        setBusy(false);
      }
      return;
    }
    try {
      if (tab === "signup") await signup(name, email, password);
      else await login(email, password);
      router.push(redirect);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? (err.message ?? "Something went wrong.")
          : "Something went wrong. Please try again."
      );
    } finally {
      setBusy(false);
    }
  }

  async function handleDemoLogin(customerId: string) {
    setDemoBusyId(customerId);
    try {
      await loginDemo(customerId);
      router.push(redirect);
    } finally {
      setDemoBusyId(null);
    }
  }

  return (
    <div className="mx-auto max-w-md px-4 py-16">
      <h1 className="text-2xl font-bold text-slate-900">
        {tab === "signup" ? "Create an account" : tab === "admin" ? "Admin log in" : "Log in"}
      </h1>

      <div className="mt-4 flex rounded-md border border-slate-200 bg-slate-50 p-1 text-sm font-medium">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => {
              setTab(t.id);
              setError(null);
              setPassword("");
            }}
            className={`flex-1 rounded px-3 py-1.5 ${tab === t.id ? "bg-white text-slate-900 shadow-sm" : "text-slate-500"}`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "admin" && (
        <p className="mt-4 text-sm text-slate-500">
          Staff only. Enter the admin password (<code className="font-mono">ADMIN_PASSWORD</code>) to open the admin
          panel.
        </p>
      )}

      <form onSubmit={handleSubmit} className="mt-6 space-y-3">
        {tab === "signup" && (
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Name</label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
        )}
        {tab !== "admin" && (
          <div>
            <label className="mb-1 block text-sm font-medium text-slate-700">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
            />
          </div>
        )}
        <div>
          <label className="mb-1 block text-sm font-medium text-slate-700">
            {tab === "admin" ? "Admin password" : "Password"}
          </label>
          <input
            type="password"
            required
            minLength={tab === "signup" ? 8 : undefined}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          {tab === "signup" && <p className="mt-1 text-xs text-slate-400">At least 8 characters.</p>}
        </div>

        {error && <p className="text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={busy}
          className="w-full rounded-md bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
        >
          {busy ? "Please wait…" : tab === "signup" ? "Create account" : tab === "admin" ? "Log in as admin" : "Log in"}
        </button>
      </form>

      {tab !== "admin" && (
        <div className="mt-8 border-t border-slate-200 pt-4">
          <button onClick={() => setShowDemo((s) => !s)} className="text-sm font-medium text-slate-500 hover:text-slate-700">
            {showDemo ? "Hide" : "Or continue with a"} demo account →
          </button>

          {showDemo && (
            <div className="mt-3 space-y-2">
              <p className="text-xs text-slate-400">
                ⚠️ Demo only: pre-seeded customers with no password, for quick testing.
              </p>
              {customers.map((c) => (
                <button
                  key={c.id}
                  disabled={demoBusyId !== null}
                  onClick={() => handleDemoLogin(c.id)}
                  className="flex w-full items-center justify-between rounded-md border border-slate-200 bg-white px-4 py-2.5 text-left hover:border-blue-300 hover:bg-blue-50 disabled:opacity-60"
                >
                  <span className="font-medium text-slate-900">{c.name}</span>
                  <span className="text-xs text-slate-400">{c.id}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
