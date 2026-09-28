export type Customer = {
  id: string;
  name: string;
};

export type SessionInfo = {
  customer_id: string;
  conversation_id: string;
  name: string;
};

export type Product = {
  sku: string;
  name: string;
  category: string | null;
  description: string | null;
  image_url: string | null;
  price_cents: number | null;
  stock_level: number | null;
  availability_note?: string;
  relevance_score?: number;
};

export type PrepareOrderItem = {
  sku: string;
  name: string;
  quantity: number;
  unit_price_cents: number;
};

export type PrepareResult = {
  success: boolean;
  confirmation_id?: number;
  items?: PrepareOrderItem[];
  total_cents?: number;
  total_display?: string;
  expires_at?: string;
  note?: string;
  error?: string;
  errors?: { sku: string; name?: string; error: string }[];
};

export type ConfirmResult = {
  success: boolean;
  order_id?: number;
  status?: string;
  items?: PrepareOrderItem[];
  total_cents?: number;
  total_display?: string;
  error?: string;
  details?: unknown;
};

export type OrderSummary = {
  order_id: number;
  status: string;
  created_at: string;
  item_count: number;
  total_cents: number;
  total_display: string;
  tracking_number?: string | null;
};

export type ListOrdersResult = {
  success: boolean;
  count: number;
  orders: OrderSummary[];
};

export type OrderStatusResult = {
  success: boolean;
  order_id: number;
  status: string;
  created_at: string;
  items: { sku: string; quantity: number; unit_price_cents: number }[];
  total_cents: number;
  total_display: string;
  tracking_number?: string | null;
  carrier?: string | null;
  shipped_at?: string | null;
  delivered_at?: string | null;
  error?: string;
};

export type ChatResponse = {
  reply: string;
  escalated: boolean;
};

// --- Admin panel (api/routers/admin.py) ---

export type AdminSummary = {
  orders_by_status: Record<string, number>;
  returns_by_status: Record<string, number>;
  open_escalations: number;
  low_stock_count: number;
  low_stock_threshold: number;
};

export type AdminOrderSummary = {
  order_id: number;
  customer_id: string;
  customer_name: string | null;
  status: string;
  created_at: string;
  item_count: number;
  total_cents: number;
  tracking_number: string | null;
  carrier: string | null;
};

export type AdminReturn = {
  return_id: number;
  order_id: number;
  customer_id: string;
  customer_name: string | null;
  reason: string;
  status: string;
  resolution: string | null;
  created_at: string;
  updated_at: string | null;
};

export type AdminOrderDetail = AdminOrderSummary & {
  customer_email: string | null;
  shipped_at: string | null;
  delivered_at: string | null;
  items: { sku: string; name: string | null; quantity: number; unit_price_cents: number }[];
  returns: AdminReturn[];
};

export type AdminEscalation = {
  escalation_id: number;
  customer_id: string;
  customer_name: string | null;
  conversation_id: string | null;
  reason: string;
  status: string;
  assigned_agent: string | null;
  resolution: string | null;
  created_at: string;
  updated_at: string | null;
};

export type AdminInventoryItem = {
  sku: string;
  name: string;
  price_cents: number;
  stock_level: number;
};
