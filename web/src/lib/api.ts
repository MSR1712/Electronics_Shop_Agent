/**
 * Every call here goes to the FastAPI layer (api/ in the backend repo) —
 * this file is the ONLY place the storefront talks to the network.
 * Product listing/detail, checkout prepare/confirm, order status/cancel,
 * and chat are all thin wrappers around the FastAPI endpoints, which
 * themselves only ever call tools/order_tools.py and tools/product_tools.py
 * via .invoke(...). No order-creation logic lives on this side.
 */
import type {
  AdminEscalation,
  AdminInventoryItem,
  AdminOrderDetail,
  AdminOrderSummary,
  AdminReturn,
  AdminSummary,
  ChatResponse,
  ConfirmResult,
  Customer,
  ListOrdersResult,
  OrderStatusResult,
  PrepareResult,
  Product,
  SessionInfo,
} from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// Same host as API_BASE, ws(s):// scheme — used by the voice widget's
// WebSocket connection to api/routers/voice.py's /ws/voice endpoint.
export const WS_BASE = API_BASE.replace(/^http/, "ws");

export class ApiError extends Error {
  status: number;
  body: unknown;

  constructor(status: number, body: unknown) {
    const detail =
      body && typeof body === "object" && "detail" in body
        ? (body as { detail: unknown }).detail
        : body;
    super(typeof detail === "string" ? detail : `Request failed (${status})`);
    this.status = status;
    this.body = body;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      ...(options.headers ?? {}),
    },
  });

  const contentType = res.headers.get("content-type") ?? "";
  const body = contentType.includes("application/json") ? await res.json() : await res.text();

  if (!res.ok) {
    throw new ApiError(res.status, body);
  }
  return body as T;
}

/**
 * checkout/prepare and checkout/confirm return their tool's own
 * {success:false, error/errors} JSON as the HTTPException `detail` when the
 * tool call didn't succeed (see api/routers/checkout.py). This unwraps that
 * shape so the UI can show the real reason (e.g. "only 1 in stock").
 */
export function errorDetail(err: unknown): { error?: string; errors?: { sku: string; name?: string; error: string }[] } | null {
  if (!(err instanceof ApiError)) return null;
  if (err.body && typeof err.body === "object" && "detail" in err.body) {
    return (err.body as { detail: { error?: string; errors?: { sku: string; name?: string; error: string }[] } }).detail;
  }
  return null;
}

function toQueryString(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined && value !== "") search.set(key, String(value));
  }
  const qs = search.toString();
  return qs ? `?${qs}` : "";
}

export const api = {
  listCustomers: () => request<Customer[]>("/api/customers"),

  createSession: (customerId: string) =>
    request<SessionInfo>("/api/session", {
      method: "POST",
      body: JSON.stringify({ customer_id: customerId }),
    }),

  signup: (name: string, email: string, password: string) =>
    request<SessionInfo>("/api/auth/signup", {
      method: "POST",
      body: JSON.stringify({ name, email, password }),
    }),

  login: (email: string, password: string) =>
    request<SessionInfo>("/api/auth/login", {
      method: "POST",
      body: JSON.stringify({ email, password }),
    }),

  async getSession(): Promise<SessionInfo | null> {
    try {
      return await request<SessionInfo>("/api/session");
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) return null;
      throw err;
    }
  },

  logout: () => request<{ success: boolean }>("/api/logout", { method: "POST" }),

  listProducts: (params: { query?: string; category?: string; limit?: number } = {}) =>
    request<{ products: Product[] }>(`/api/products${toQueryString(params)}`),

  listCategories: () => request<{ categories: string[] }>("/api/categories"),

  getProduct: (sku: string) => request<Product>(`/api/products/${encodeURIComponent(sku)}`),

  prepareCheckout: (items: { sku: string; quantity: number }[]) =>
    request<PrepareResult>("/api/checkout/prepare", {
      method: "POST",
      body: JSON.stringify({ items }),
    }),

  confirmCheckout: (confirmationId: number) =>
    request<ConfirmResult>("/api/checkout/confirm", {
      method: "POST",
      body: JSON.stringify({ confirmation_id: confirmationId }),
    }),

  listOrders: () => request<ListOrdersResult>("/api/orders"),

  getOrder: (orderId: number) => request<OrderStatusResult>(`/api/orders/${orderId}`),

  cancelOrder: (orderId: number) =>
    request<{ success: boolean; order_id: number; status: string }>(
      `/api/orders/${orderId}/cancel`,
      { method: "POST" }
    ),

  chat: (message: string) =>
    request<ChatResponse>("/api/chat", {
      method: "POST",
      body: JSON.stringify({ message }),
    }),
};

/**
 * Admin panel calls (api/routers/admin.py). Authenticated by the separate
 * cw_admin cookie (api/admin_session.py), never the customer session, and
 * every state change goes through the backend's atomic admin functions.
 */
export const adminApi = {
  login: (password: string) =>
    request<{ success: boolean }>("/api/admin/login", {
      method: "POST",
      body: JSON.stringify({ password }),
    }),

  logout: () => request<{ success: boolean }>("/api/admin/logout", { method: "POST" }),

  me: () => request<{ admin: boolean }>("/api/admin/me"),

  summary: () => request<AdminSummary>("/api/admin/summary"),

  listOrders: (status?: string) =>
    request<{ orders: AdminOrderSummary[] }>(`/api/admin/orders${toQueryString({ status })}`),

  getOrder: (orderId: number) => request<AdminOrderDetail>(`/api/admin/orders/${orderId}`),

  markProcessing: (orderId: number) =>
    request<{ success: boolean }>(`/api/admin/orders/${orderId}/processing`, { method: "POST" }),

  markShipped: (orderId: number, trackingNumber: string, carrier?: string) =>
    request<{ success: boolean }>(`/api/admin/orders/${orderId}/ship`, {
      method: "POST",
      body: JSON.stringify({ tracking_number: trackingNumber, carrier: carrier || null }),
    }),

  markDelivered: (orderId: number) =>
    request<{ success: boolean }>(`/api/admin/orders/${orderId}/deliver`, { method: "POST" }),

  listReturns: (status?: string) =>
    request<{ returns: AdminReturn[] }>(`/api/admin/returns${toQueryString({ status })}`),

  approveReturn: (returnId: number, resolution?: string) =>
    request<{ success: boolean }>(`/api/admin/returns/${returnId}/approve`, {
      method: "POST",
      body: JSON.stringify({ resolution: resolution || null }),
    }),

  rejectReturn: (returnId: number, resolution?: string) =>
    request<{ success: boolean }>(`/api/admin/returns/${returnId}/reject`, {
      method: "POST",
      body: JSON.stringify({ resolution: resolution || null }),
    }),

  refundReturn: (returnId: number) =>
    request<{ success: boolean }>(`/api/admin/returns/${returnId}/refund`, { method: "POST" }),

  listEscalations: (status?: string) =>
    request<{ escalations: AdminEscalation[] }>(`/api/admin/escalations${toQueryString({ status })}`),

  updateEscalation: (
    escalationId: number,
    changes: { status?: string; assigned_agent?: string | null; resolution?: string | null }
  ) =>
    request<AdminEscalation>(`/api/admin/escalations/${escalationId}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),

  listInventory: (params: { q?: string; lowStock?: boolean } = {}) =>
    request<{ items: AdminInventoryItem[]; total: number }>(
      `/api/admin/inventory${toQueryString({ q: params.q, low_stock: params.lowStock ? "true" : undefined })}`
    ),

  updateInventory: (sku: string, changes: { price_cents?: number; stock_delta?: number }) =>
    request<AdminInventoryItem>(`/api/admin/inventory/${encodeURIComponent(sku)}`, {
      method: "PATCH",
      body: JSON.stringify(changes),
    }),
};

/** Human-readable message for any admin API failure. */
export function adminErrorMessage(err: unknown, fallback = "Something went wrong."): string {
  const detail = errorDetail(err);
  if (detail && typeof detail === "object" && detail.error) return detail.error;
  if (err instanceof ApiError) return err.message;
  return fallback;
}
