"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api, ApiError } from "@/lib/api";
import type { Product } from "@/lib/types";
import { formatCents } from "@/lib/format";
import { useCart } from "@/context/CartContext";

export default function ProductDetailPage() {
  const { sku } = useParams<{ sku: string }>();
  const router = useRouter();
  const { addItem } = useCart();

  const [product, setProduct] = useState<Product | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [quantity, setQuantity] = useState(1);
  const [added, setAdded] = useState(false);

  useEffect(() => {
    setNotFound(false);
    setProduct(null);
    api
      .getProduct(sku)
      .then(setProduct)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 404) setNotFound(true);
      });
  }, [sku]);

  if (notFound) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-16 text-center">
        <p className="text-lg font-medium text-slate-700">Product not found.</p>
        <Link href="/products" className="mt-4 inline-block text-blue-600 hover:text-blue-700">
          Back to all products
        </Link>
      </div>
    );
  }

  if (!product) {
    return <div className="py-16 text-center text-slate-500">Loading…</div>;
  }

  const outOfStock = product.stock_level !== null && product.stock_level <= 0;
  const maxQty = product.stock_level ?? 99;

  return (
    <div className="mx-auto max-w-5xl px-4 py-8 sm:px-6">
      <div className="grid grid-cols-1 gap-8 md:grid-cols-2">
        <div className="flex aspect-square items-center justify-center rounded-lg border border-slate-200 bg-slate-50 p-8">
          {product.image_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={product.image_url} alt={product.name} className="h-full w-full object-contain" />
          ) : (
            <span className="text-6xl text-slate-300">⚙</span>
          )}
        </div>

        <div>
          {product.category && (
            <span className="text-xs font-semibold uppercase tracking-wide text-blue-600">{product.category}</span>
          )}
          <h1 className="mt-1 text-2xl font-bold text-slate-900">{product.name}</h1>
          <p className="mt-1 text-sm text-slate-500">SKU: {product.sku}</p>

          <p className="mt-4 text-3xl font-bold text-slate-900">{formatCents(product.price_cents)}</p>
          <p className="mt-1 text-sm text-slate-500">
            {product.availability_note ?? (outOfStock ? "Out of stock" : `${product.stock_level} in stock`)}
          </p>

          {!outOfStock && product.price_cents !== null && (
            <div className="mt-6 flex items-center gap-3">
              <label htmlFor="qty" className="text-sm font-medium text-slate-700">
                Quantity
              </label>
              <input
                id="qty"
                type="number"
                min={1}
                max={maxQty}
                value={quantity}
                onChange={(e) => setQuantity(Math.max(1, Math.min(maxQty, Number(e.target.value) || 1)))}
                className="w-20 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
              />
            </div>
          )}

          <div className="mt-4 flex gap-3">
            <button
              disabled={outOfStock || product.price_cents === null}
              onClick={() => {
                addItem({ sku: product.sku, name: product.name, price_cents: product.price_cents! }, quantity);
                setAdded(true);
                setTimeout(() => setAdded(false), 1500);
              }}
              className="rounded-md bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:bg-slate-300"
            >
              {added ? "Added ✓" : "Add to cart"}
            </button>
            <button
              onClick={() => router.push("/cart")}
              className="rounded-md border border-slate-300 px-5 py-2.5 text-sm font-medium text-slate-700 hover:bg-slate-50"
            >
              View cart
            </button>
          </div>

          {product.description && (
            <div className="mt-8 whitespace-pre-line border-t border-slate-200 pt-6 text-sm leading-6 text-slate-600">
              {product.description}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
