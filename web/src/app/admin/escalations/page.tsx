"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { adminApi, adminErrorMessage } from "@/lib/api";
import type { AdminEscalation } from "@/lib/types";
import StatusBadge, { statusLabel } from "@/components/admin/StatusBadge";

const STATUSES = ["open", "assigned", "waiting_for_customer", "waiting_for_agent", "resolved", "closed"];

export default function AdminEscalationsPage() {
  return (
    <Suspense fallback={<p className="text-slate-500">Loading…</p>}>
      <AdminEscalationsView />
    </Suspense>
  );
}

function AdminEscalationsView() {
  const router = useRouter();
  const status = useSearchParams().get("status") ?? "";
  const [escalations, setEscalations] = useState<AdminEscalation[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => {
    adminApi
      .listEscalations(status || undefined)
      .then((res) => setEscalations(res.escalations))
      .catch((err) => setError(adminErrorMessage(err, "Could not load escalations.")));
  }, [status]);

  useEffect(() => {
    setEscalations(null);
    setError(null);
    load();
  }, [load]);

  return (
    <div className="max-w-5xl">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-slate-900">Escalations</h1>
        <select
          value={status}
          onChange={(e) =>
            router.push(e.target.value ? `/admin/escalations?status=${e.target.value}` : "/admin/escalations")
          }
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
        >
          <option value="">All statuses</option>
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {statusLabel(s)}
            </option>
          ))}
        </select>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}
      {!error && escalations === null && <p className="text-slate-500">Loading…</p>}
      {escalations && escalations.length === 0 && <p className="text-slate-500">No escalations.</p>}

      <div className="space-y-3">
        {escalations?.map((e) => <EscalationCard key={e.escalation_id} escalation={e} onChanged={load} />)}
      </div>
    </div>
  );
}

function EscalationCard({ escalation, onChanged }: { escalation: AdminEscalation; onChanged: () => void }) {
  const [status, setStatus] = useState(escalation.status);
  const [agent, setAgent] = useState(escalation.assigned_agent ?? "");
  const [resolution, setResolution] = useState(escalation.resolution ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const dirty =
    status !== escalation.status ||
    agent !== (escalation.assigned_agent ?? "") ||
    resolution !== (escalation.resolution ?? "");

  async function save() {
    setBusy(true);
    setError(null);
    setSaved(false);
    try {
      await adminApi.updateEscalation(escalation.escalation_id, {
        status,
        assigned_agent: agent.trim() || null,
        resolution: resolution.trim() || null,
      });
      setSaved(true);
      onChanged();
    } catch (err) {
      setError(adminErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white p-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-3">
          <span className="font-semibold text-slate-900">Escalation #{escalation.escalation_id}</span>
          <StatusBadge status={escalation.status} />
        </div>
        <span className="text-sm text-slate-500">{new Date(escalation.created_at).toLocaleString()}</span>
      </div>
      <p className="mt-2 text-sm text-slate-600">
        {escalation.customer_name ?? "—"} <span className="text-slate-400">{escalation.customer_id}</span>
        {escalation.conversation_id && (
          <span className="text-slate-400"> · conversation {escalation.conversation_id}</span>
        )}
      </p>
      <p className="mt-2 whitespace-pre-wrap text-sm text-slate-900">{escalation.reason}</p>

      <div className="mt-4 grid gap-3 sm:grid-cols-[auto_1fr]">
        <select
          value={status}
          onChange={(e) => setStatus(e.target.value)}
          className="rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
        >
          {STATUSES.map((s) => (
            <option key={s} value={s}>
              {statusLabel(s)}
            </option>
          ))}
        </select>
        <input
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
          placeholder="Assigned agent"
          className="rounded-md border border-slate-300 px-3 py-2 text-sm"
        />
        <textarea
          value={resolution}
          onChange={(e) => setResolution(e.target.value)}
          placeholder="Resolution / notes"
          rows={2}
          className="rounded-md border border-slate-300 px-3 py-2 text-sm sm:col-span-2"
        />
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          disabled={busy || !dirty}
          onClick={() => void save()}
          className="rounded-md bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-500 disabled:opacity-60"
        >
          {busy ? "Saving…" : "Save"}
        </button>
        {saved && !dirty && <span className="text-sm text-green-600">Saved</span>}
        {error && <span className="text-sm text-red-600">{error}</span>}
      </div>
    </div>
  );
}
