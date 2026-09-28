"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { api } from "@/lib/api";
import { useCart } from "@/context/CartContext";
import { useSession } from "@/context/SessionContext";

export default function Header() {
  const { count } = useCart();
  const { session, loading, logout } = useSession();
  const [categories, setCategories] = useState<string[]>([]);
  const pathname = usePathname();

  useEffect(() => {
    api
      .listCategories()
      .then((res) => setCategories(res.categories))
      .catch(() => setCategories([]));
  }, []);

  // The admin panel (app/admin/layout.tsx) has its own chrome.
  if (pathname?.startsWith("/admin")) return null;

  return (
    <header className="sticky top-0 z-40 border-b border-slate-200 bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-7xl items-center gap-6 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2 text-lg font-bold tracking-tight text-slate-900">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-blue-600 text-white">⚡</span>
          CircuitWorks
        </Link>

        <nav className="hidden flex-1 items-center gap-1 md:flex">
          <Link
            href="/products"
            className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
          >
            All Products
          </Link>
          {categories.map((c) => (
            <Link
              key={c}
              href={`/products?category=${encodeURIComponent(c)}`}
              className="rounded-md px-3 py-2 text-sm font-medium text-slate-700 hover:bg-slate-100"
            >
              {c}
            </Link>
          ))}
        </nav>

        <div className="ml-auto flex items-center gap-4">
          {!loading && (
            <div className="hidden items-center gap-4 text-sm text-slate-600 sm:flex">
              {session ? (
                <>
                  <Link href="/orders" className="font-medium hover:text-slate-900">
                    My Orders
                  </Link>
                  <button onClick={() => void logout()} className="hover:text-slate-900" title={session.customer_id}>
                    {session.name} · <span className="text-blue-600">Log out</span>
                  </button>
                </>
              ) : (
                <Link
                  href={`/login?redirect=${encodeURIComponent(pathname ?? "/")}`}
                  className="font-medium text-blue-600 hover:text-blue-700"
                >
                  Log in
                </Link>
              )}
            </div>
          )}

          <Link href="/cart" className="relative flex items-center rounded-md p-2 hover:bg-slate-100" aria-label="Cart">
            <CartIcon />
            {count > 0 && (
              <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-blue-600 px-1 text-xs font-semibold text-white">
                {count}
              </span>
            )}
          </Link>
        </div>
      </div>
    </header>
  );
}

function CartIcon() {
  return (
    <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.8} className="h-6 w-6 text-slate-700">
      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 3h1.386c.51 0 .955.343 1.087.835l.383 1.437M7.5 14.25a3 3 0 0 0-3 3h15.75m-12.75-3h11.218c1.121-2.3 1.98-4.684 2.57-7.152.078-.323-.145-.648-.478-.648H5.106M7.5 14.25 5.106 5.272M6 20.25a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Zm12.75 0a.75.75 0 1 1-1.5 0 .75.75 0 0 1 1.5 0Z" />
    </svg>
  );
}
