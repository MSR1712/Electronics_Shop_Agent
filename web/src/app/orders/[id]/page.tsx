"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { OrderStatusResult } from "@/lib/types";
import { formatCents } from "@/lib/format";

const CANCELLABLE = new Set(["pending", "confirmed"]);

export default function OrderStatusPage() {
  const { id } = useParams<{ id: string }>();
  const orderId = Number(id);

  const [order, setOrder] = useState<OrderStatusResult | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    setNotFound(false);
    api
      .getOrder(orderId)
      .then(setOrder)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) setNotFound(true);
      });
  }, [orderId]);

  useEffect(() => {
    load();
  }, [load]);

  if (notFound) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-16 text-center">
        <p className="text-lg font-medium text-slate-700">Order not found.</p>
        <Link href="/products" className="mt-4 inline-block text-blue-600 hover:text-blue-700">
          Back to shopping
        </Link>
      </div>
    );
  }

  if (!order) {
    return <div className="py-16 text-center text-slate-500">Loading…</div>;
  }

  async function handleCancel() {
    setBusy(true);
    setError(null);
    try {
      await api.cancelOrder(orderId);
      load();
    } catch {
      setError("Could not cancel this order.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 sm:px-6">
      <h1 className="mb-1 text-2xl font-bold text-slate-900">Order #{order.order_id}</h1>
      <p className="mb-6 text-sm text-slate-500">Placed {new Date(order.created_at).toLocaleString()}</p>

      <span
        className={`inline-block rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide ${
          order.status === "cancelled"
            ? "bg-red-100 text-red-700"
            : order.status === "confirmed"
              ? "bg-green-100 text-green-700"
              : "bg-slate-100 text-slate-700"
        }`}
      >
        {order.status}
      </span>

      {order.tracking_number && (
        <div className="mt-4 rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm">
          <p className="font-medium text-slate-900">
            Tracking number: <span className="font-mono">{order.tracking_number}</span>
            {order.carrier && <span className="text-slate-500"> ({order.carrier})</span>}
          </p>
          {order.shipped_at && (
            <p className="mt-1 text-slate-500">Shipped {new Date(order.shipped_at).toLocaleString()}</p>
          )}
          {order.delivered_at && (
            <p className="mt-1 text-slate-500">Delivered {new Date(order.delivered_at).toLocaleString()}</p>
          )}
        </div>
      )}

      <div className="mt-6 divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
        {order.items.map((item, i) => (
          <div key={`${item.sku}-${i}`} className="flex justify-between p-4 text-sm">
            <span>
              {item.sku} × {item.quantity}
            </span>
            <span className="font-medium">{formatCents(item.unit_price_cents * item.quantity)}</span>
          </div>
        ))}
      </div>

      <div className="mt-4 flex justify-between text-lg font-semibold text-slate-900">
        <span>Total</span>
        <span>{order.total_display}</span>
      </div>

      {error && <p className="mt-4 text-sm text-red-600">{error}</p>}

      {CANCELLABLE.has(order.status) && (
        <button
          disabled={busy}
          onClick={handleCancel}
          className="mt-6 rounded-md border border-red-300 px-5 py-2.5 text-sm font-medium text-red-600 hover:bg-red-50 disabled:opacity-60"
        >
          {busy ? "Cancelling…" : "Cancel order"}
        </button>
      )}
    </div>
  );
}
