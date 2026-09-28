"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "@/lib/api";
import type { SessionInfo } from "@/lib/types";

type SessionContextValue = {
  session: SessionInfo | null;
  loading: boolean;
  /** Bare customer_id, no password — the seeded demo customers only. */
  loginDemo: (customerId: string) => Promise<void>;
  /** Real password login (api/routers/auth.py). */
  login: (email: string, password: string) => Promise<void>;
  signup: (name: string, email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
};

const SessionContext = createContext<SessionContextValue | undefined>(undefined);

// One browser session = one (customer_id, conversation_id) pair, set by
// POST /api/session and read back here. Both the manual checkout flow and
// the chat widget read customer/conversation identity from this same
// context, so "add to cart via chat" and "add to cart via the product page"
// land in the same conversation thread (see tools/order_tools.py, which
// scopes pending confirmations to exactly that pair).
export function SessionProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<SessionInfo | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    api
      .getSession()
      .then((data) => {
        if (!cancelled) setSession(data);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const loginDemo = useCallback(async (customerId: string) => {
    const data = await api.createSession(customerId);
    setSession(data);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const data = await api.login(email, password);
    setSession(data);
  }, []);

  const signup = useCallback(async (name: string, email: string, password: string) => {
    const data = await api.signup(name, email, password);
    setSession(data);
  }, []);

  const logout = useCallback(async () => {
    await api.logout();
    setSession(null);
  }, []);

  return (
    <SessionContext.Provider value={{ session, loading, loginDemo, login, signup, logout }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionContextValue {
  const ctx = useContext(SessionContext);
  if (!ctx) throw new Error("useSession must be used within SessionProvider");
  return ctx;
}
