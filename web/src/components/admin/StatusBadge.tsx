const TONES: Record<string, string> = {
  // orders
  pending: "bg-amber-100 text-amber-800",
  confirmed: "bg-blue-100 text-blue-700",
  processing: "bg-indigo-100 text-indigo-700",
  shipped: "bg-violet-100 text-violet-700",
  delivered: "bg-green-100 text-green-700",
  cancelled: "bg-red-100 text-red-700",
  return_requested: "bg-amber-100 text-amber-800",
  refunded: "bg-slate-200 text-slate-700",
  // returns
  requested: "bg-amber-100 text-amber-800",
  approved: "bg-blue-100 text-blue-700",
  rejected: "bg-red-100 text-red-700",
  received: "bg-indigo-100 text-indigo-700",
  // escalations
  open: "bg-red-100 text-red-700",
  assigned: "bg-blue-100 text-blue-700",
  waiting_for_customer: "bg-amber-100 text-amber-800",
  waiting_for_agent: "bg-amber-100 text-amber-800",
  resolved: "bg-green-100 text-green-700",
  closed: "bg-slate-200 text-slate-700",
};

export function statusLabel(status: string): string {
  return status.replace(/_/g, " ");
}

export default function StatusBadge({ status }: { status: string }) {
  return (
    <span
      className={`inline-block whitespace-nowrap rounded-full px-2.5 py-1 text-xs font-semibold uppercase tracking-wide ${
        TONES[status] ?? "bg-slate-100 text-slate-700"
      }`}
    >
      {statusLabel(status)}
    </span>
  );
}
