import { Suspense } from "react";
import ProductsView from "./ProductsView";

export default function ProductsPage() {
  return (
    <Suspense fallback={<div className="py-12 text-center text-slate-500">Loading…</div>}>
      <ProductsView />
    </Suspense>
  );
}
