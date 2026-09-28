"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api, errorDetail } from "@/lib/api";
import type { PrepareResult } from "@/lib/types";
import { formatCents } from "@/lib/format";
import { useCart } from "@/context/CartContext";
import { useSession } from "@/context/SessionContext";

// Mirrors the chat agent's own confirmation rule (agents/order_agent.py):
// prepare, show the customer exactly what they're about to buy, and only
// call confirm once they explicitly click Confirm — never skip straight to
// confirm from the cart.
export default function CheckoutPage() {
  const { session, loading: sessionLoading } = useSession();
  const { items, subtotalCents, clear } = useCart();
  const router = useRouter();

  const [prepared, setPrepared] = useState<PrepareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  if (sessionLoading) {
    return <div className="py-16 text-center text-slate-500">Loading…</div>;
  }

  if (!session) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <p className="text-lg font-medium text-slate-700">Log in to check out.</p>
        <Link
          href="/login?redirect=/checkout"
          className="mt-4 inline-block rounded-md bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
        >
          Log in
        </Link>
      </div>
    );
  }

  if (items.length === 0 && !prepared) {
    return (
      <div className="mx-auto max-w-md px-4 py-16 text-center">
        <p className="text-lg font-medium text-slate-700">Your cart is empty.</p>
        <Link href="/products" className="mt-4 inline-block text-blue-600 hover:text-blue-700">
          Browse products →
        </Link>
      </div>
    );
  }

  async function handlePrepare() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.prepareCheckout(items.map((i) => ({ sku: i.sku, quantity: i.quantity })));
      setPrepared(result);
    } catch (err) {
      const detail = errorDetail(err);
      setError(detail?.errors?.map((e) => `${e.name ?? e.sku}: ${e.error}`).join("; ") ?? detail?.error ?? "Could not prepare order.");
    } finally {
      setBusy(false);
    }
  }

  async function handleConfirm() {
    if (!prepared?.confirmation_id) return;
    setBusy(true);
    setError(null);
    try {
      const result = await api.confirmCheckout(prepared.confirmation_id);
      if (result.success && result.order_id) {
        clear();
        router.push(`/orders/${result.order_id}`);
      }
    } catch (err) {
      const detail = errorDetail(err);
      setError(detail?.error ?? "Could not confirm order.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8 sm:px-6">
      <h1 className="mb-6 text-2xl font-bold text-slate-900">Checkout</h1>

      {!prepared ? (
        <>
          <div className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
            {items.map((item) => (
              <div key={item.sku} className="flex justify-between p-4 text-sm">
                <span>
                  {item.name} × {item.quantity}
                </span>
                <span className="font-medium">{formatCents(item.price_cents * item.quantity)}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 flex justify-between text-lg font-semibold text-slate-900">
            <span>Subtotal</span>
            <span>{formatCents(subtotalCents)}</span>
          </div>
          {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
          <button
            disabled={busy}
            onClick={handlePrepare}
            className="mt-6 w-full rounded-md bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
          >
            {busy ? "Preparing…" : "Review order"}
          </button>
        </>
      ) : (
        <>
          <p className="mb-4 text-sm text-slate-600">
            Review your order below. Nothing has been charged or shipped yet — confirm to place it.
          </p>
          <div className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
            {prepared.items?.map((item) => (
              <div key={item.sku} className="flex justify-between p-4 text-sm">
                <span>
                  {item.name} × {item.quantity}
                </span>
                <span className="font-medium">{formatCents(item.unit_price_cents * item.quantity)}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 flex justify-between text-lg font-semibold text-slate-900">
            <span>Total</span>
            <span>{prepared.total_display}</span>
          </div>
          {error && <p className="mt-4 text-sm text-red-600">{error}</p>}
          <div className="mt-6 flex gap-3">
            <button
              onClick={() => setPrepared(null)}
              className="flex-1 rounded-md border border-slate-300 px-5 py-3 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              Back
            </button>
            <button
              disabled={busy}
              onClick={handleConfirm}
              className="flex-1 rounded-md bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
            >
              {busy ? "Placing order…" : "Confirm order"}
            </button>
          </div>
        </>
      )}
    </div>
  );
}
