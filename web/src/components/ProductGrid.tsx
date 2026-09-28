import Link from "next/link";
import type { Product } from "@/lib/types";
import { formatCents } from "@/lib/format";

export default function ProductGrid({ products }: { products: Product[] }) {
  if (products.length === 0) {
    return <p className="py-12 text-center text-slate-500">No products found.</p>;
  }

  return (
    <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
      {products.map((p) => (
        <ProductCard key={p.sku} product={p} />
      ))}
    </div>
  );
}

function ProductCard({ product }: { product: Product }) {
  const outOfStock = product.stock_level !== null && product.stock_level <= 0;

  return (
    <Link
      href={`/products/${encodeURIComponent(product.sku)}`}
      className="group flex flex-col overflow-hidden rounded-lg border border-slate-200 bg-white transition hover:-translate-y-0.5 hover:shadow-md"
    >
      <div className="flex aspect-square items-center justify-center bg-slate-50 p-4">
        {product.image_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img
            src={product.image_url}
            alt={product.name}
            className="h-full w-full object-contain transition group-hover:scale-105"
            loading="lazy"
          />
        ) : (
          <span className="text-3xl text-slate-300">⚙</span>
        )}
      </div>
      <div className="flex flex-1 flex-col gap-1 p-3">
        {product.category && <span className="text-xs font-medium uppercase tracking-wide text-blue-600">{product.category}</span>}
        <h3 className="line-clamp-2 text-sm font-medium text-slate-900">{product.name}</h3>
        <div className="mt-auto flex items-center justify-between pt-2">
          <span className="text-sm font-semibold text-slate-900">{formatCents(product.price_cents)}</span>
          {outOfStock ? (
            <span className="text-xs font-medium text-red-600">Out of stock</span>
          ) : (
            <span className="text-xs text-slate-500">{product.stock_level ?? "—"} in stock</span>
          )}
        </div>
      </div>
    </Link>
  );
}
