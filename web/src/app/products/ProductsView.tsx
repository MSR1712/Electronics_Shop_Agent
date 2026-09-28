"use client";

import { useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { api } from "@/lib/api";
import type { Product } from "@/lib/types";
import ProductGrid from "@/components/ProductGrid";

export default function ProductsView() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const category = searchParams.get("category") ?? "";
  const initialQuery = searchParams.get("query") ?? "";

  const [query, setQuery] = useState(initialQuery);
  const [products, setProducts] = useState<Product[]>([]);
  const [categories, setCategories] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api
      .listCategories()
      .then((res) => setCategories(res.categories))
      .catch(() => setCategories([]));
  }, []);

  useEffect(() => {
    setLoading(true);
    api
      .listProducts({ query: initialQuery || undefined, category: category || undefined, limit: 48 })
      .then((res) => setProducts(res.products))
      .catch(() => setProducts([]))
      .finally(() => setLoading(false));
  }, [initialQuery, category]);

  function updateParam(key: string, value: string) {
    const params = new URLSearchParams(searchParams.toString());
    if (value) params.set(key, value);
    else params.delete(key);
    router.push(`/products${params.toString() ? `?${params.toString()}` : ""}`);
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <div className="mb-6 flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
        <h1 className="text-2xl font-bold text-slate-900">
          {category ? category : "All Products"}
        </h1>

        <form
          onSubmit={(e) => {
            e.preventDefault();
            updateParam("query", query);
          }}
          className="flex w-full max-w-sm gap-2"
        >
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search products…"
            className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm focus:border-blue-500 focus:outline-none"
          />
          <button type="submit" className="rounded-md bg-slate-900 px-4 py-2 text-sm font-medium text-white hover:bg-slate-700">
            Search
          </button>
        </form>
      </div>

      <div className="mb-6 flex flex-wrap gap-2">
        <button
          onClick={() => updateParam("category", "")}
          className={`rounded-full border px-3 py-1 text-sm ${
            !category ? "border-blue-600 bg-blue-50 text-blue-700" : "border-slate-200 text-slate-600 hover:border-slate-300"
          }`}
        >
          All
        </button>
        {categories.map((c) => (
          <button
            key={c}
            onClick={() => updateParam("category", c)}
            className={`rounded-full border px-3 py-1 text-sm ${
              category === c ? "border-blue-600 bg-blue-50 text-blue-700" : "border-slate-200 text-slate-600 hover:border-slate-300"
            }`}
          >
            {c}
          </button>
        ))}
      </div>

      {loading ? <p className="py-12 text-center text-slate-500">Loading…</p> : <ProductGrid products={products} />}
    </div>
  );
}
