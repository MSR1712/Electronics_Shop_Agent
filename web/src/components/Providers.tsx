"use client";

import type { ReactNode } from "react";
import { SessionProvider } from "@/context/SessionContext";
import { CartProvider } from "@/context/CartContext";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <CartProvider>{children}</CartProvider>
    </SessionProvider>
  );
}
