import Link from "next/link";
import { API_BASE } from "@/lib/api";
import type { Product } from "@/lib/types";
import ProductGrid from "@/components/ProductGrid";

async function getHomeData(): Promise<{ products: Product[]; categories: string[]; apiDown: boolean }> {
  try {
    const [productsRes, categoriesRes] = await Promise.all([
      fetch(`${API_BASE}/api/products?limit=8`, { cache: "no-store" }),
      fetch(`${API_BASE}/api/categories`, { cache: "no-store" }),
    ]);
    if (!productsRes.ok || !categoriesRes.ok) throw new Error("API returned a non-OK status");
    const products: { products: Product[] } = await productsRes.json();
    const categories: { categories: string[] } = await categoriesRes.json();
    return { products: products.products, categories: categories.categories, apiDown: false };
  } catch {
    // The FastAPI backend isn't reachable (not started yet, mid-restart,
    // etc.) — degrade gracefully instead of hard-500ing the whole page.
    return { products: [], categories: [], apiDown: true };
  }
}

export default async function Home() {
  const { products, categories, apiDown } = await getHomeData();

  if (apiDown) {
    return (
      <div className="mx-auto max-w-2xl px-4 py-24 text-center">
        <p className="text-lg font-medium text-slate-700">Can’t reach the CircuitWorks API.</p>
        <p className="mt-2 text-sm text-slate-500">
          Make sure the backend is running: <code className="rounded bg-slate-100 px-1.5 py-0.5">uvicorn api.main:app --reload --port 8000</code>,
          then refresh this page.
        </p>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
      <section className="mb-10 overflow-hidden rounded-2xl bg-slate-900 px-8 py-16 text-white">
        <p className="text-sm font-semibold uppercase tracking-widest text-blue-400">Electronics & Robotics</p>
        <h1 className="mt-2 max-w-xl text-4xl font-bold tracking-tight sm:text-5xl">
          Components for your next build.
        </h1>
        <p className="mt-4 max-w-lg text-slate-300">
          ICs, MCUs, sensors, motors, and power modules — in stock and ready to ship. Need help picking a part?
          Our chat assistant in the corner can help, or place an order right here.
        </p>
        <Link
          href="/products"
          className="mt-6 inline-block rounded-md bg-blue-600 px-5 py-2.5 text-sm font-semibold text-white hover:bg-blue-500"
        >
          Browse all products
        </Link>
      </section>

      <section className="mb-10">
        <h2 className="mb-4 text-lg font-semibold text-slate-900">Shop by category</h2>
        <div className="flex flex-wrap gap-2">
          {categories.map((c) => (
            <Link
              key={c}
              href={`/products?category=${encodeURIComponent(c)}`}
              className="rounded-full border border-slate-200 bg-white px-4 py-1.5 text-sm font-medium text-slate-700 hover:border-blue-300 hover:text-blue-700"
            >
              {c}
            </Link>
          ))}
        </div>
      </section>

      <section>
        <div className="mb-4 flex items-center justify-between">
          <h2 className="text-lg font-semibold text-slate-900">Featured products</h2>
          <Link href="/products" className="text-sm font-medium text-blue-600 hover:text-blue-700">
            View all →
          </Link>
        </div>
        <ProductGrid products={products} />
      </section>
    </div>
  );
}
