"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, type FormEvent } from "react";
import { useParams } from "next/navigation";
import { adminApi, adminErrorMessage, ApiError } from "@/lib/api";
import type { AdminOrderDetail } from "@/lib/types";
import { formatCents } from "@/lib/format";
import StatusBadge from "@/components/admin/StatusBadge";

export default function AdminOrderDetailPage() {
  const { id } = useParams<{ id: string }>();
  const orderId = Number(id);

  const [order, setOrder] = useState<AdminOrderDetail | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [tracking, setTracking] = useState("");
  const [carrier, setCarrier] = useState("");

  const load = useCallback(() => {
    adminApi
      .getOrder(orderId)
      .then(setOrder)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) setNotFound(true);
        else setError(adminErrorMessage(err, "Could not load this order."));
      });
  }, [orderId]);

  useEffect(() => {
    load();
  }, [load]);

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      load();
    } catch (err) {
      setError(adminErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function handleShip(e: FormEvent) {
    e.preventDefault();
    void run(() => adminApi.markShipped(orderId, tracking.trim(), carrier.trim()));
  }

  if (notFound) {
    return (
      <div>
        <p className="text-lg font-medium text-slate-700">Order not found.</p>
        <Link href="/admin/orders" className="mt-2 inline-block text-blue-600 hover:text-blue-700">
          Back to orders
        </Link>
      </div>
    );
  }
  if (!order) return error ? <p className="text-sm text-red-600">{error}</p> : <p className="text-slate-500">Loading…</p>;

  const canProcess = order.status === "confirmed";
  const canShip = order.status === "confirmed" || order.status === "processing";
  const canDeliver = order.status === "shipped";

  return (
    <div className="max-w-3xl">
      <Link href="/admin/orders" className="text-sm text-slate-500 hover:text-slate-900">
        ← All orders
      </Link>
      <div className="mt-2 flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold text-slate-900">Order #{order.order_id}</h1>
        <StatusBadge status={order.status} />
      </div>
      <p className="mt-1 text-sm text-slate-500">
        Placed {new Date(order.created_at).toLocaleString()} by {order.customer_name ?? "—"} ({order.customer_id}
        {order.customer_email && `, ${order.customer_email}`})
      </p>

      <div className="mt-6 divide-y divide-slate-100 rounded-lg border border-slate-200 bg-white">
        {order.items.map((item, i) => (
          <div key={`${item.sku}-${i}`} className="flex justify-between gap-4 p-4 text-sm">
            <span>
              <span className="font-medium text-slate-900">{item.name ?? item.sku}</span>{" "}
              <span className="text-slate-400">{item.sku}</span> × {item.quantity}
            </span>
            <span className="font-medium">{formatCents(item.unit_price_cents * item.quantity)}</span>
          </div>
        ))}
        <div className="flex justify-between p-4 font-semibold text-slate-900">
          <span>Total</span>
          <span>{formatCents(order.total_cents)}</span>
        </div>
      </div>

      <section className="mt-6 rounded-lg border border-slate-200 bg-white p-5">
        <h2 className="mb-3 font-semibold text-slate-900">Fulfillment</h2>

        {order.tracking_number && (
          <div className="mb-4 text-sm text-slate-600">
            <p>
              Tracking: <span className="font-mono text-slate-900">{order.tracking_number}</span>
              {order.carrier && ` (${order.carrier})`}
            </p>
            {order.shipped_at && <p>Shipped {new Date(order.shipped_at).toLocaleString()}</p>}
            {order.delivered_at && <p>Delivered {new Date(order.delivered_at).toLocaleString()}</p>}
          </div>
        )}

        {!canProcess && !canShip && !canDeliver && (
          <p className="text-sm text-slate-500">No fulfillment actions available for this status.</p>
        )}

        <div className="flex flex-wrap items-end gap-3">
          {canProcess && (
            <button
              disabled={busy}
              onClick={() => void run(() => adminApi.markProcessing(orderId))}
              className="rounded-md border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              Start processing
            </button>
          )}
          {canDeliver && (
            <button
              disabled={busy}
              onClick={() => void run(() => adminApi.markDelivered(orderId))}
              className="rounded-md bg-green-600 px-4 py-2 text-sm font-semibold text-white hover:bg-green-500 disabled:opacity-60"
            >
              Mark delivered
            </button>
          )}
        </div>

        {canShip && (
          <form onSubmit={handleShip} className="mt-4 flex flex-wrap items-end gap-3">
            <label className="text-sm">
              <span className="mb-1 block font-medium text-slate-700">Tracking number</span>
              <input
                value={tracking}
                onChange={(e) => setTracking(e.target.value)}
                required
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <label className="text-sm">
              <span className="mb-1 block font-medium text-slate-700">Carrier (optional)</span>
              <input
                value={carrier}
                onChange={(e) => setCarrier(e.target.value)}
                className="rounded-md border border-slate-300 px-3 py-2 text-sm"
              />
            </label>
            <button
              type="submit"
              disabled={busy || !tracking.trim()}
              className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
            >
              Mark shipped
            </button>
          </form>
        )}

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}
      </section>

      {order.returns.length > 0 && (
        <section className="mt-6 rounded-lg border border-slate-200 bg-white p-5">
          <h2 className="mb-3 font-semibold text-slate-900">Returns</h2>
          <ul className="space-y-2 text-sm">
            {order.returns.map((r) => (
              <li key={r.return_id} className="flex flex-wrap items-center gap-2">
                <span className="font-medium">Return #{r.return_id}</span>
                <StatusBadge status={r.status} />
                <span className="text-slate-600">{r.reason}</span>
              </li>
            ))}
          </ul>
          <Link href="/admin/returns" className="mt-3 inline-block text-sm text-blue-600 hover:text-blue-700">
            Manage returns →
          </Link>
        </section>
      )}
    </div>
  );
}
