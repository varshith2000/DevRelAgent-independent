/**
 * Shared API response types.
 *
 * These mirror the backend Pydantic models so the UI can stay type-safe without
 * duplicating shape knowledge at every call site.
 */

export type RiskLevel = 'low' | 'medium' | 'high' | 'critical';

export interface ApprovalRequest {
  approval_id: string;
  action_type: string;
  plan: string[];
  risk_level: RiskLevel;
  metadata?: Record<string, unknown>;
  timeout_seconds: number;
  created_at: string;
}

export interface ApprovalStatus {
  pending_approvals: ApprovalRequest[];
  total_pending: number;
}

export interface ApprovalHistoryEntry {
  approval_id: string;
  action_type: string;
  risk_level: RiskLevel;
  approved: boolean | null;
  user: string | null;
  reason: string | null;
  created_at: string | null;
  responded_at: string | null;
  duration_seconds: number | null;
  plan: string[];
  metadata: Record<string, unknown>;
}

export interface ApprovalHistory {
  history: ApprovalHistoryEntry[];
  total: number;
  limit: number;
}

export interface Workspace {
  id: string;
  name: string;
  slug: string;
  external_id: string | null;
  created_at: string;
  role: string | null;
}

export interface Member {
  user_id: string;
  email: string;
  name: string | null;
  role: string;
}

export interface Project {
  id: string;
  workspace_id: string;
  name: string;
  slug: string;
  description: string | null;
  status: string;
  created_at: string;
  archived_at: string | null;
}

export interface ApiKey {
  id: string;
  name: string;
  prefix: string;
  scopes: string[];
  created_at: string;
  last_used_at: string | null;
  expires_at: string | null;
  revoked_at: string | null;
}

export interface ApiKeyCreated extends ApiKey {
  /** Returned exactly once, at creation time. */
  key: string;
}
