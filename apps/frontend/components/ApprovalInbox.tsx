"use client";

import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, RefreshCw, ShieldCheck, XCircle } from 'lucide-react';
import { apiFetch } from '../lib/api';
import { getIdentity } from '../lib/auth';
import type { ApprovalHistory, ApprovalRequest, ApprovalStatus } from '../lib/types';
import { ApprovalCard } from './ApprovalCard';

const POLL_INTERVAL_MS = 5000;

function formatWhen(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString();
}

/**
 * Human-in-the-loop inbox: pending approvals with approve/reject actions and a
 * recent-decision history. Polls while open so approvals raised on the backend
 * appear without a manual refresh.
 */
export function ApprovalInbox({ className = '' }: { className?: string }) {
  const [pending, setPending] = useState<ApprovalRequest[]>([]);
  const [history, setHistory] = useState<ApprovalHistory['history']>([]);
  const [reasons, setReasons] = useState<Record<string, string>>({});
  const [busyId, setBusyId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [pendingResponse, historyResponse] = await Promise.all([
        apiFetch('/approvals/pending'),
        apiFetch('/approvals/history?limit=25'),
      ]);
      if (!pendingResponse.ok) throw new Error(`pending request failed (${pendingResponse.status})`);
      if (!historyResponse.ok) throw new Error(`history request failed (${historyResponse.status})`);

      const status = (await pendingResponse.json()) as ApprovalStatus;
      const recent = (await historyResponse.json()) as ApprovalHistory;

      setPending(status.pending_approvals ?? []);
      setHistory(recent.history ?? []);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load approvals');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    const timer = setInterval(() => void load(), POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [load]);

  const decide = useCallback(
    async (approvalId: string, approved: boolean) => {
      setBusyId(approvalId);
      setError(null);
      try {
        const response = await apiFetch(`/approvals/${approvalId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            approved,
            user: getIdentity().email,
            reason: reasons[approvalId] || undefined,
          }),
        });
        if (!response.ok) {
          let detail = `Decision failed (${response.status}).`;
          try { const payload = await response.json(); if (typeof payload.detail === 'string') detail = payload.detail; } catch { /* Use status text. */ }
          throw new Error(detail);
        }

        setPending((current) => current.filter((item) => item.approval_id !== approvalId));
        setReasons((current) => {
          const next = { ...current };
          delete next[approvalId];
          return next;
        });
        await load();
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to record decision');
        await load();
      } finally {
        setBusyId(null);
      }
    },
    [load, reasons],
  );

  return (
    <div className={`approval-inbox-shell ${className}`}>
      <div className="approval-inbox-toolbar flex items-center justify-between px-6 py-4 border-b border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
        <div className="flex items-center space-x-2">
          <ShieldCheck className="w-5 h-5 text-gray-600 dark:text-gray-400" />
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">
            Pending approvals
          </h2>
          <span className="ml-2 px-2 py-0.5 rounded-full text-xs font-semibold bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-200">
            {pending.length}
          </span>
        </div>
        <button
          onClick={() => void load()}
          className="p-2 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700 rounded-lg transition-colors"
          title="Refresh"
        >
          <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="approval-inbox-error mx-6 mt-4 p-4 bg-red-50 dark:bg-red-900/20 border border-red-500 rounded-lg" role="alert">
          <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
        </div>
      )}

      <div className="approval-inbox-content flex-1 overflow-y-auto px-6 py-4 space-y-6 bg-gray-50 dark:bg-gray-900">
        {pending.length === 0 ? (
          <div className="text-center py-12">
            <CheckCircle2 className="w-12 h-12 mx-auto text-gray-400 dark:text-gray-600 mb-4" />
            <p className="text-gray-500 dark:text-gray-400">No approvals waiting</p>
            <p className="text-sm text-gray-400 dark:text-gray-500 mt-1">
              High-risk actions will appear here for review
            </p>
          </div>
        ) : (
          pending.map((approval) => (
            <div key={approval.approval_id} className="space-y-2">
              <input
                value={reasons[approval.approval_id] ?? ''}
                onChange={(event) =>
                  setReasons((current) => ({
                    ...current,
                    [approval.approval_id]: event.target.value,
                  }))
                }
                placeholder="Optional note sent with your decision"
                className="approval-reason-input w-full rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <ApprovalCard
                approvalId={approval.approval_id}
                actionType={approval.action_type}
                plan={approval.plan}
                riskLevel={approval.risk_level}
                metadata={approval.metadata}
                isLoading={busyId === approval.approval_id}
                onApprove={() => void decide(approval.approval_id, true)}
                onReject={() => void decide(approval.approval_id, false)}
              />
            </div>
          ))
        )}

        <section className="pt-4">
          <h3 className="text-sm font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-3">
            Recent decisions
          </h3>
          {history.length === 0 ? (
            <p className="text-sm text-gray-400 dark:text-gray-500">No decisions recorded yet.</p>
          ) : (
            <div className="overflow-x-auto rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800">
              <table className="approval-history-table min-w-full text-sm">
                <thead className="bg-gray-50 dark:bg-gray-900 text-gray-500 dark:text-gray-400">
                  <tr>
                    <th className="px-4 py-2 text-left font-medium">Action</th>
                    <th className="px-4 py-2 text-left font-medium">Decision</th>
                    <th className="px-4 py-2 text-left font-medium">By</th>
                    <th className="px-4 py-2 text-left font-medium">When</th>
                    <th className="px-4 py-2 text-left font-medium">Reason</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-100 dark:divide-gray-700">
                  {history.map((entry) => (
                    <tr key={entry.approval_id}>
                      <td className="px-4 py-2 text-gray-900 dark:text-white">
                        {entry.action_type}
                      </td>
                      <td className="px-4 py-2">
                        <span
                          className={`inline-flex items-center space-x-1 ${
                            entry.approved ? 'text-green-600 dark:text-green-400' : 'text-red-600 dark:text-red-400'
                          }`}
                        >
                          {entry.approved ? (
                            <CheckCircle2 className="w-4 h-4" />
                          ) : (
                            <XCircle className="w-4 h-4" />
                          )}
                          <span>{entry.approved ? 'Approved' : 'Rejected'}</span>
                        </span>
                      </td>
                      <td className="px-4 py-2 text-gray-600 dark:text-gray-400">
                        {entry.user ?? '—'}
                      </td>
                      <td className="px-4 py-2 text-gray-600 dark:text-gray-400">
                        {formatWhen(entry.responded_at ?? entry.created_at)}
                      </td>
                      <td className="px-4 py-2 text-gray-600 dark:text-gray-400">
                        {entry.reason ?? '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>
      </div>
    </div>
  );
}

export default ApprovalInbox;
