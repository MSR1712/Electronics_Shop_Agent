"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { adminApi, adminErrorMessage } from "@/lib/api";
import type { AdminSummary } from "@/lib/types";
import StatusBadge from "@/components/admin/StatusBadge";

export default function AdminDashboardPage() {
  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    adminApi
      .summary()
      .then(setSummary)
      .catch((err) => setError(adminErrorMessage(err, "Could not load the dashboard.")));
  }, []);

  if (error) return <p className="text-sm text-red-600">{error}</p>;
  if (!summary) return <p className="text-slate-500">Loading…</p>;

  const o = summary.orders_by_status;
  const r = summary.returns_by_status;
  const tiles = [
    { label: "Orders to fulfill", value: (o.confirmed ?? 0) + (o.processing ?? 0), href: "/admin/orders?status=confirmed" },
    { label: "In transit", value: o.shipped ?? 0, href: "/admin/orders?status=shipped" },
    { label: "Returns to review", value: r.requested ?? 0, href: "/admin/returns?status=requested" },
    { label: "Refunds to process", value: r.approved ?? 0, href: "/admin/returns?status=approved" },
    { label: "Open escalations", value: summary.open_escalations, href: "/admin/escalations" },
    {
      label: `Low stock (≤ ${summary.low_stock_threshold})`,
      value: summary.low_stock_count,
      href: "/admin/inventory?low_stock=1",
    },
  ];

  return (
    <div className="max-w-5xl">
      <h1 className="mb-6 text-2xl font-bold text-slate-900">Dashboard</h1>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3">
        {tiles.map((t) => (
          <Link
            key={t.label}
            href={t.href}
            className="rounded-lg border border-slate-200 bg-white p-5 hover:border-blue-300 hover:shadow-sm"
          >
            <p className="text-sm text-slate-500">{t.label}</p>
            <p className={`mt-1 text-3xl font-bold ${t.value > 0 ? "text-slate-900" : "text-slate-400"}`}>{t.value}</p>
          </Link>
        ))}
      </div>

      <h2 className="mb-3 mt-10 text-lg font-semibold text-slate-900">Orders by status</h2>
      <div className="flex flex-wrap gap-3">
        {Object.entries(o).map(([status, count]) => (
          <Link
            key={status}
            href={`/admin/orders?status=${status}`}
            className="flex items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2 hover:border-blue-300"
          >
            <StatusBadge status={status} />
            <span className="font-semibold text-slate-900">{count}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
