"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { adminApi, adminErrorMessage } from "@/lib/api";
import type { AdminInventoryItem } from "@/lib/types";
import { formatCents } from "@/lib/format";

export default function AdminInventoryPage() {
  return (
    <Suspense fallback={<p className="text-slate-500">Loading…</p>}>
      <AdminInventoryView />
    </Suspense>
  );
}

function AdminInventoryView() {
  const router = useRouter();
  const lowStock = useSearchParams().get("low_stock") === "1";
  const [items, setItems] = useState<AdminInventoryItem[] | null>(null);
  const [total, setTotal] = useState(0);
  const [filter, setFilter] = useState("");
  const [query, setQuery] = useState("");
  const [error, setError] = useState<string | null>(null);

  // Debounce typing so each keystroke doesn't hit the API.
  useEffect(() => {
    const t = setTimeout(() => setQuery(filter.trim()), 300);
    return () => clearTimeout(t);
  }, [filter]);

  const load = useCallback(() => {
    adminApi
      .listInventory({ q: query || undefined, lowStock })
      .then((res) => {
        setItems(res.items);
        setTotal(res.total);
      })
      .catch((err) => setError(adminErrorMessage(err, "Could not load inventory.")));
  }, [query, lowStock]);

  useEffect(() => {
    setError(null);
    load();
  }, [load]);

  function replaceItem(updated: AdminInventoryItem) {
    setItems((prev) => prev?.map((i) => (i.sku === updated.sku ? updated : i)) ?? prev);
  }

  return (
    <div className="max-w-5xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">Inventory</h1>
        <div className="flex flex-wrap items-center gap-3">
          <input
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            placeholder="Filter by SKU or name"
            className="rounded-md border border-slate-300 px-3 py-2 text-sm"
          />
          <label className="flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={lowStock}
              onChange={(e) => router.push(e.target.checked ? "/admin/inventory?low_stock=1" : "/admin/inventory")}
            />
            Low stock only
          </label>
        </div>
      </div>

      <p className="mb-4 text-sm text-slate-500">
        Stock changes are relative (+ to restock, − to write off) so they can&apos;t clobber orders placed at the same
        time. New prices apply to new checkouts only; existing orders keep the price they were placed at.
      </p>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {!error && items === null && <p className="text-slate-500">Loading…</p>}
      {items && items.length === 0 && <p className="text-slate-500">No items.</p>}
      {items && items.length > 0 && items.length < total && (
        <p className="mb-2 text-sm text-slate-500">
          Showing {items.length} of {total.toLocaleString()} — search to narrow it down.
        </p>
      )}

      {items && items.length > 0 && (
        <div className="overflow-x-auto rounded-lg border border-slate-200 bg-white">
          <table className="w-full text-left text-sm">
            <thead className="border-b border-slate-200 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-3">SKU</th>
                <th className="px-4 py-3">Name</th>
                <th className="px-4 py-3 text-right">Price</th>
                <th className="px-4 py-3 text-right">Stock</th>
                <th className="px-4 py-3">Adjust</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((item) => (
                <InventoryRow key={item.sku} item={item} onUpdated={replaceItem} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function InventoryRow({ item, onUpdated }: { item: AdminInventoryItem; onUpdated: (i: AdminInventoryItem) => void }) {
  const [delta, setDelta] = useState("");
  const [price, setPrice] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const deltaNum = delta.trim() === "" ? 0 : Number(delta);
  const priceCents = price.trim() === "" ? undefined : Math.round(Number(price) * 100);
  const valid =
    Number.isInteger(deltaNum) &&
    (priceCents === undefined || (Number.isFinite(priceCents) && priceCents >= 0)) &&
    (deltaNum !== 0 || priceCents !== undefined);

  async function apply() {
    setBusy(true);
    setError(null);
    try {
      const updated = await adminApi.updateInventory(item.sku, {
        ...(deltaNum !== 0 ? { stock_delta: deltaNum } : {}),
        ...(priceCents !== undefined ? { price_cents: priceCents } : {}),
      });
      onUpdated(updated);
      setDelta("");
      setPrice("");
    } catch (err) {
      setError(adminErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <tr className="align-top">
      <td className="px-4 py-3 font-mono text-xs text-slate-600">{item.sku}</td>
      <td className="px-4 py-3 text-slate-900">{item.name}</td>
      <td className="px-4 py-3 text-right">{formatCents(item.price_cents)}</td>
      <td className={`px-4 py-3 text-right font-semibold ${item.stock_level <= 5 ? "text-red-600" : "text-slate-900"}`}>
        {item.stock_level}
      </td>
      <td className="px-4 py-3">
        <div className="flex flex-wrap items-center gap-2">
          <input
            value={delta}
            onChange={(e) => setDelta(e.target.value)}
            placeholder="± qty"
            inputMode="numeric"
            className="w-20 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
          <input
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            placeholder="New $ price"
            inputMode="decimal"
            className="w-28 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
          <button
            disabled={busy || !valid}
            onClick={() => void apply()}
            className="rounded-md bg-blue-600 px-3 py-1.5 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-50"
          >
            Apply
          </button>
        </div>
        {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
      </td>
    </tr>
  );
}
