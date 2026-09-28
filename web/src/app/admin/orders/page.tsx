"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { adminApi, adminErrorMessage } from "@/lib/api";
import type { AdminOrderSummary } from "@/lib/types";
import { formatCents } from "@/lib/format";
import StatusBadge, { statusLabel } from "@/components/admin/StatusBadge";

const STATUSES = [
  "pending",
  "confirmed",
  "processing",
  "shipped",
  "delivered",
  "cancelled",
  "return_requested",
  "refunded",
];

export default function AdminOrdersPage() {
  return (
    <Suspense fallback={<p className="text-slate-500">Loading…</p>}>
      <AdminOrdersView />
    </Suspense>
  );
}

function AdminOrdersView() {
  const router = useRouter();
  const status = useSearchParams().get("status") ?? "";
  const [orders, setOrders] = useState<AdminOrderSummary[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setOrders(null);
    setError(null);
    adminApi
      .listOrders(status || undefined)
      .then((res) => setOrders(res.orders))
      .catch((err) => setError(adminErrorMessage(err, "Could not load orders.")));
  }, [status]);

  return (
    <div className="max-w-5xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">Orders</h1>
        <select
          value={status}
          onChange={(e) => router.push(e.target.value ? `/admin/orders?status=${e.target.value}` : "/admin/orders")}
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
      {!error && orders === null && <p className="text-slate-500">Loading…</p>}
      {orders && orders.length === 0 && <p className="text-slate-500">No orders.</p>}

      {orders && orders.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">Order</th>
                <th className="px-4 py-3">Customer</th>
                <th className="px-4 py-3">Placed</th>
                <th className="px-4 py-3">Items</th>
                <th className="px-4 py-3 text-right">Total</th>
                <th className="px-4 py-3">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {orders.map((o) => (
                <tr key={o.order_id} className="hover:bg-slate-50">
                  <td className="px-4 py-3 font-medium">
                    <Link href={`/admin/orders/${o.order_id}`} className="text-blue-600 hover:text-blue-700">
                      #{o.order_id}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    {o.customer_name ?? "—"} <span className="text-slate-400">{o.customer_id}</span>
                  </td>
                  <td className="px-4 py-3 text-slate-600">{new Date(o.created_at).toLocaleString()}</td>
                  <td className="px-4 py-3">{o.item_count}</td>
                  <td className="px-4 py-3 text-right font-medium">{formatCents(o.total_cents)}</td>
                  <td className="px-4 py-3">
                    <StatusBadge status={o.status} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
