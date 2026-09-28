"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { OrderSummary } from "@/lib/types";
import { useSession } from "@/context/SessionContext";

export default function OrdersListPage() {
  const { session, loading: sessionLoading } = useSession();
  const [orders, setOrders] = useState<OrderSummary[] | null>(null);

  useEffect(() => {
    if (!session) return;
    api
      .listOrders()
      .then((res) => setOrders(res.orders))
      .catch(() => setOrders([]));
  }, [session]);

  if (sessionLoading) {
    return <div className="py-16 text-center text-slate-500">Loading…</div>;
  }

  if (!session) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <p className="text-lg font-medium text-slate-700">Log in to see your orders.</p>
        <Link
          href="/login?redirect=/orders"
          className="mt-4 inline-block rounded-md bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
        >
          Log in
        </Link>
      </div>
    );
  }

  if (orders === null) {
    return <div className="py-16 text-center text-slate-500">Loading…</div>;
  }

  if (orders.length === 0) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <p className="text-lg font-medium text-slate-700">No orders yet.</p>
        <Link href="/products" className="mt-4 inline-block text-blue-600 hover:text-blue-700">
          Start shopping
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 sm:px-6">
      <h1 className="mb-6 text-2xl font-bold text-slate-900">My Orders</h1>

      <div className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
        {orders.map((o) => (
          <Link
            key={o.order_id}
            href={`/orders/${o.order_id}`}
            className="flex items-center justify-between p-4 text-sm hover:bg-slate-50"
          >
            <div>
              <p className="font-medium text-slate-900">
                Order #{o.order_id} · {o.item_count} item{o.item_count === 1 ? "" : "s"}
              </p>
              <p className="text-slate-500">
                {new Date(o.created_at).toLocaleDateString()}
                {o.tracking_number && ` · Tracking: ${o.tracking_number}`}
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span className="font-medium text-slate-900">{o.total_display}</span>
              <span
                className={`rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${
                  o.status === "cancelled"
                    ? "bg-red-100 text-red-700"
                    : o.status === "delivered"
                      ? "bg-green-100 text-green-700"
                      : "bg-slate-100 text-slate-700"
                }`}
              >
                {o.status}
              </span>
            </div>
          </Link>
        ))}
      </div>
    </div>
  );
}
