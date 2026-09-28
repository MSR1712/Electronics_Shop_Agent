"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { adminApi, adminErrorMessage } from "@/lib/api";
import type { AdminReturn } from "@/lib/types";
import StatusBadge, { statusLabel } from "@/components/admin/StatusBadge";

const STATUSES = ["requested", "approved", "rejected", "refunded"];

export default function AdminReturnsPage() {
  return (
    <Suspense fallback={<p className="text-slate-500">Loading…</p>}>
      <AdminReturnsView />
    </Suspense>
  );
}

function AdminReturnsView() {
  const router = useRouter();
  const status = useSearchParams().get("status") ?? "";
  const [returns, setReturns] = useState<AdminReturn[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    adminApi
      .listReturns(status || undefined)
      .then((res) => setReturns(res.returns))
      .catch((err) => setError(adminErrorMessage(err, "Could not load returns.")));
  }, [status]);

  useEffect(() => {
    setReturns(null);
    setError(null);
    load();
  }, [load]);

  return (
    <div className="max-w-5xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">Returns</h1>
        <select
          value={status}
          onChange={(e) => router.push(e.target.value ? `/admin/returns?status=${e.target.value}` : "/admin/returns")}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {statusLabel(s)}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {!error && returns === null && <p className="text-slate-500">Loading…</p>}
      {returns && returns.length === 0 && <p className="text-slate-500">No returns.</p>}

      <div className="space-y-3">
        {returns?.map((r) => <ReturnCard key={r.return_id} ret={r} onChanged={load} />)}
      </div>
    </div>
  );
}

function ReturnCard({ ret, onChanged }: { ret: AdminReturn; onChanged: () => void }) {
  const [resolution, setResolution] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
    } catch (err) {
      setError(adminErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="font-semibold text-slate-900">Return #{ret.return_id}</span>
          <StatusBadge status={ret.status} />
        </div>
        <span className="text-sm text-slate-500">{new Date(ret.created_at).toLocaleString()}</span>
      </div>
      <p className="mt-2 text-sm text-slate-600">
        <Link href={`/admin/orders/${ret.order_id}`} className="text-blue-600 hover:text-blue-700">
          Order #{ret.order_id}
        </Link>{" "}
        · {ret.customer_name ?? "—"} <span className="text-slate-400">{ret.customer_id}</span>
      </p>
      <p className="mt-2 text-sm text-slate-900">
        <span className="font-medium">Reason:</span> {ret.reason}
      </p>
      {ret.resolution && (
        <p className="mt-1 text-sm text-slate-600">
          <span className="font-medium">Resolution:</span> {ret.resolution}
        </p>
      )}

      {ret.status === "requested" && (
        <div className="mt-4 flex flex-wrap items-center gap-3">
          <input
            value={resolution}
            onChange={(e) => setResolution(e.target.value)}
            placeholder="Resolution note (optional)"
            className="min-w-60 flex-1 rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <button
            disabled={busy}
            onClick={() => void run(() => adminApi.approveReturn(ret.return_id, resolution.trim()))}
            className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
          >
            Approve
          </button>
          <button
            disabled={busy}
            onClick={() => void run(() => adminApi.rejectReturn(ret.return_id, resolution.trim()))}
            className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
          >
            Reject
          </button>
        </div>
      )}

      {ret.status === "approved" && (
        <button
          disabled={busy}
          onClick={() => {
            if (window.confirm(`Refund return #${ret.return_id}? This can only be done once.`)) {
              void run(() => adminApi.refundReturn(ret.return_id));
            }
          }}
          className="mt-4 rounded-md bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-500 disabled:opacity-60"
        >
          Process refund
        </button>
      )}

      {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
    </div>
  );
}
