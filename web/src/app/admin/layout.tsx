"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState, type FormEvent, type ReactNode } from "react";
import { adminApi, adminErrorMessage, ApiError } from "@/lib/api";

const NAV = [
  { href: "/admin", label: "Dashboard" },
  { href: "/admin/orders", label: "Orders" },
  { href: "/admin/returns", label: "Returns" },
  { href: "/admin/escalations", label: "Escalations" },
  { href: "/admin/inventory", label: "Inventory" },
];

type AuthState = "checking" | "signed-out" | "signed-in" | "disabled";

// The whole /admin tree is gated here on the separate cw_admin cookie
// (api/admin_session.py). The storefront Header/ChatWidget hide themselves
// on /admin routes, so this layout owns the full page chrome.
export default function AdminLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const [auth, setAuth] = useState<AuthState>("checking");

  useEffect(() => {
    adminApi
      .me()
      .then(() => setAuth("signed-in"))
      .catch((err) => setAuth(err instanceof ApiError && err.status === 503 ? "disabled" : "signed-out"));
  }, []);

  async function handleLogout() {
    await adminApi.logout().catch(() => undefined);
    setAuth("signed-out");
  }

  if (auth === "checking") {
    return <div className="py-16 text-center text-slate-500">Loading…</div>;
  }

  if (auth === "disabled") {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <p className="text-lg font-medium text-slate-700">The admin panel is disabled.</p>
        <p className="mt-2 text-sm text-slate-500">
          Set <code className="font-mono">ADMIN_PASSWORD</code> in the backend&apos;s <code className="font-mono">.env</code> and
          restart the API.
        </p>
      </div>
    );
  }

  if (auth === "signed-out") {
    return <AdminLogin onSuccess={() => setAuth("signed-in")} />;
  }

  return (
    <div className="flex min-h-screen flex-col md:flex-row">
      <aside className="border-b border-slate-800 bg-slate-900 text-slate-200 md:w-56 md:shrink-0 md:border-b-0 md:border-r">
        <div className="flex items-center justify-between px-4 py-4 md:block">
          <Link href="/admin" className="flex items-center gap-2 text-lg font-bold text-white">
            <span className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-600">⚡</span>
            Admin
          </Link>
          <Link href="/" className="text-xs text-slate-400 hover:text-white md:mt-2 md:block">
            ← Back to store
          </Link>
        </div>
        <nav className="flex gap-1 overflow-x-auto px-2 pb-3 md:flex-col md:pb-0">
          {NAV.map((item) => {
            const active = item.href === "/admin" ? pathname === "/admin" : pathname?.startsWith(item.href);
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium ${
                  active ? "bg-slate-800 text-white" : "text-slate-300 hover:bg-slate-800 hover:text-white"
                }`}
              >
                {item.label}
              </Link>
            );
          })}
        </nav>
        <div className="hidden px-4 py-4 md:block">
          <button onClick={() => void handleLogout()} className="text-sm text-slate-400 hover:text-white">
            Log out
          </button>
        </div>
      </aside>
      <div className="flex-1 overflow-x-auto px-4 py-6 sm:px-8">
        <div className="mb-4 text-right md:hidden">
          <button onClick={() => void handleLogout()} className="text-sm text-slate-500 hover:text-slate-900">
            Log out
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function AdminLogin({ onSuccess }: { onSuccess: () => void }) {
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await adminApi.login(password);
      onSuccess();
    } catch (err) {
      setError(adminErrorMessage(err, "Could not log in."));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center px-4">
      <form onSubmit={handleSubmit} className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
        <h1 className="mb-1 text-xl font-bold text-slate-900">CircuitWorks Admin</h1>
        <p className="mb-5 text-sm text-slate-500">Enter the admin password to continue.</p>
        <label className="mb-1 block text-sm font-medium text-slate-700" htmlFor="admin-password">
          Password
        </label>
        <input
          id="admin-password"
          type="password"
          autoFocus
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
        />
        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
        <button
          type="submit"
          disabled={busy || !password}
          className="mt-5 w-full rounded-md bg-blue-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
        >
          {busy ? "Logging in…" : "Log in"}
        </button>
        <Link href="/" className="mt-4 block text-center text-sm text-slate-500 hover:text-slate-900">
          Back to store
        </Link>
      </form>
    </div>
  );
}
