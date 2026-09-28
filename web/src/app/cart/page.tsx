"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCart } from "@/context/CartContext";
import { formatCents } from "@/lib/format";

export default function CartPage() {
  const { items, setQuantity, removeItem, subtotalCents } = useCart();
  const router = useRouter();

  if (items.length === 0) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center">
        <p className="text-lg font-medium text-slate-700">Your cart is empty.</p>
        <Link href="/products" className="mt-4 inline-block text-blue-600 hover:text-blue-700">
          Browse products →
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6">
      <h1 className="mb-6 text-2xl font-bold text-slate-900">Your cart</h1>

      <div className="divide-y divide-slate-200 rounded-lg border border-slate-200 bg-white">
        {items.map((item) => (
          <div key={item.sku} className="flex items-center gap-4 p-4">
            <div className="flex-1">
              <Link href={`/products/${encodeURIComponent(item.sku)}`} className="font-medium text-slate-900 hover:text-blue-600">
                {item.name}
              </Link>
              <p className="text-sm text-slate-500">{formatCents(item.price_cents)} each</p>
            </div>
            <input
              type="number"
              min={1}
              value={item.quantity}
              onChange={(e) => setQuantity(item.sku, Number(e.target.value) || 0)}
              className="w-16 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
            <p className="w-20 text-right font-medium text-slate-900">{formatCents(item.price_cents * item.quantity)}</p>
            <button onClick={() => removeItem(item.sku)} className="text-sm text-slate-400 hover:text-red-600">
              Remove
            </button>
          </div>
        ))}
      </div>

      <div className="mt-6 flex items-center justify-between">
        <span className="text-lg font-semibold text-slate-900">Subtotal</span>
        <span className="text-lg font-bold text-slate-900">{formatCents(subtotalCents)}</span>
      </div>

      <button
        onClick={() => router.push("/checkout")}
        className="mt-6 w-full rounded-md bg-blue-600 px-5 py-3 text-sm font-semibold text-white hover:bg-blue-500"
      >
        Proceed to checkout
      </button>
    </div>
  );
}
