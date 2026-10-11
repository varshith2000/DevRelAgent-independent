/**
 * Backend-less adapter for the static demo build.
 *
 * When `NEXT_PUBLIC_DEMO_MODE=true`, `apiFetch` routes here instead of hitting
 * the FastAPI service: read endpoints return the checked-in fixtures from
 * `demo-data.ts`, mutations update this module's in-memory state (so approving
 * an action or creating an API key behaves like the real thing for the length
 * of the page visit), and `demoStream` emulates the dashboard SSE feed.
 *
 * This module is imported dynamically only in demo builds, so neither the
 * fixtures nor this adapter end up in a production bundle.
 */

import { createDemoState, demoChatReply, type DemoAlert, type DemoState } from './demo-data';
import type { ApiKey, ApiKeyCreated, Project } from './types';

const state: DemoState = createDemoState();

/** Small artificial latency so loading and typing states are visible. */
function latencyMs(): number {
  return 120 + Math.floor(Math.random() * 260);
}

function json(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function problem(detail: string, status = 404): Response {
  return json({ detail }, status);
}

function sleep(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

function channel(projectId: string): ApiKey[] {
  if (!state.apiKeys[projectId]) state.apiKeys[projectId] = [];
  return state.apiKeys[projectId];
}

function readBody(init: RequestInit): Record<string, unknown> {
  if (typeof init.body !== 'string' || init.body.length === 0) return {};
  try {
    const parsed: unknown = JSON.parse(init.body);
    return parsed && typeof parsed === 'object' ? (parsed as Record<string, unknown>) : {};
  } catch {
    return {};
  }
}

function randomId(prefix: string): string {
  return `${prefix}_${Math.random().toString(36).slice(2, 10)}`;
}

/**
 * Full-canvas replacement for `fetch` in demo builds.
 *
 * @param path Root-relative API path, optionally with a query string.
 * @param init Standard fetch options; `method` and a JSON `body` are honoured.
 */
export async function demoFetch(path: string, init: RequestInit = {}): Promise<Response> {
  const url = new URL(path, 'https://demo.devrelagent.local');
  const route = url.pathname.replace(/\/+$/, '') || '/';
  const method = (init.method ?? 'GET').toUpperCase();

  await sleep(latencyMs());

  if (method === 'GET') {
    switch (route) {
      case '/health':
        return json({ status: 'ok', demo: true, version: '2026.10.05-demo', checks: state.services });
      case '/auth/me':
        return json({
          email: state.members[0].email,
          name: state.members[0].name,
          workspace_name: state.workspace.name,
          workspace_slug: state.workspace.slug,
          role: state.workspace.role,
          project_id: state.projects[0].id,
        });
      case '/workspaces/current':
        return json(state.workspace);
      case '/workspaces/current/members':
        return json(state.members);
      case '/projects':
        return json(state.projects);
      case '/dashboard/status':
        return json({
          demo: true,
          checked_at: state.servicesMonitoredAt,
          services: state.services,
        });
      case '/dashboard/alerts': {
        const limit = Number(url.searchParams.get('limit') ?? '20');
        const alerts = state.alerts.slice(0, Number.isFinite(limit) ? limit : 20);
        return json({ alerts, total: state.alerts.length, demo: true });
      }
      case '/approvals/pending':
        return json({ pending_approvals: state.pending, total_pending: state.pending.length });
      case '/approvals/history': {
        const limit = Number(url.searchParams.get('limit') ?? '25');
        const history = state.history.slice(0, Number.isFinite(limit) ? limit : 25);
        return json({ history, total: state.history.length, limit });
      }
    }

    const keyList = route.match(/^\/projects\/([^/]+)\/api-keys$/);
    if (keyList) return json(channel(decodeURIComponent(keyList[1])));
  }

  if (method === 'POST') {
    switch (route) {
      case '/chat': {
        const body = readBody(init);
        const message = typeof body.message === 'string' ? body.message : '';
        const reply = demoChatReply(message);
        return json({
          ...reply,
          session_id: typeof body.session_id === 'string' ? body.session_id : randomId('sess'),
          demo: true,
        });
      }
      case '/projects': {
        const body = readBody(init);
        const name = typeof body.name === 'string' && body.name.trim() ? body.name.trim() : 'Untitled project';
        const project: Project = {
          id: randomId('prj_demo'),
          workspace_id: state.workspace.id,
          name,
          slug: name.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, ''),
          description: 'Created in the demo build; resets on reload.',
          status: 'active',
          created_at: new Date().toISOString(),
          archived_at: null,
        };
        state.projects.push(project);
        return json(project, 201);
      }
      default:
        break;
    }

    const archive = route.match(/^\/projects\/([^/]+)\/archive$/);
    if (archive) {
      const project = state.projects.find((item) => item.id === archive[1]);
      if (!project) return problem('Project not found.', 404);
      project.status = 'archived';
      project.archived_at = new Date().toISOString();
      return json(project);
    }

    const createKey = route.match(/^\/projects\/([^/]+)\/api-keys$/);
    if (createKey) {
      const projectId = decodeURIComponent(createKey[1]);
      const body = readBody(init);
      const name = typeof body.name === 'string' && body.name.trim() ? body.name.trim() : 'demo-key';
      const secret = Math.random().toString(36).slice(2, 14);
      const prefix = `drk_live_${secret.slice(0, 4)}`;
      const key: ApiKeyCreated = {
        id: randomId('key_demo'),
        name,
        prefix,
        scopes: Array.isArray(body.scopes) ? (body.scopes as string[]) : [],
        created_at: new Date().toISOString(),
        last_used_at: null,
        expires_at: null,
        revoked_at: null,
        key: `${prefix}_${secret}`,
      };
      channel(projectId).push(key);
      return json(key, 201);
    }

    const decision = route.match(/^\/approvals\/([^/]+)$/);
    if (decision) {
      const approvalId = decodeURIComponent(decision[1]);
      const index = state.pending.findIndex((item) => item.approval_id === approvalId);
      if (index === -1) return problem('Approval not found or already decided.', 404);

      const body = readBody(init);
      const [approval] = state.pending.splice(index, 1);
      const respondedAt = new Date().toISOString();
      state.history.unshift({
        approval_id: approvalId,
        action_type: approval.action_type,
        risk_level: approval.risk_level,
        approved: body.approved !== false,
        user: typeof body.user === 'string' ? body.user : null,
        reason: typeof body.reason === 'string' ? body.reason : null,
        created_at: approval.created_at,
        responded_at: respondedAt,
        duration_seconds: Math.round(
          (Date.parse(respondedAt) - Date.parse(approval.created_at)) / 1000,
        ),
        plan: approval.plan,
        metadata: approval.metadata ?? {},
      });
      return json({ approval_id: approvalId, approved: body.approved !== false, responded_at: respondedAt });
    }
  }

  if (method === 'DELETE') {
    const revoke = route.match(/^\/projects\/([^/]+)\/api-keys\/([^/]+)$/);
    if (revoke) {
      const projectId = decodeURIComponent(revoke[1]);
      const keyId = decodeURIComponent(revoke[2]);
      const keys = channel(projectId);
      const index = keys.findIndex((item) => item.id === keyId);
      if (index === -1) return problem('API key not found.', 404);
      keys.splice(index, 1);
      return json({ revoked: keyId });
    }
  }

  return problem(`The demo build does not implement ${method} ${route}.`, 404);
}

export interface DemoStreamHandlers {
  onOpen?: () => void;
  onMessage?: (raw: string) => void;
  onError?: () => void;
}

/** Extra synthetic alerts pushed into the live feed so it visibly updates. */
const LIVE_ALERTS: Array<Omit<DemoAlert, 'id' | 'timestamp'>> = [
  {
    type: 'alert',
    severity: 'warning',
    service: 'orders-api',
    message: 'Connection pool still saturated: pool.wait_ms holding at 4,800 ms.',
    error_rate: 38.4,
    metadata: { environment: 'demo', check: 'pool' },
  },
  {
    type: 'health_check',
    severity: 'info',
    service: 'postgres-primary',
    message: 'Active connections 96/100 — approaching the configured ceiling.',
    metadata: { environment: 'demo', connections: 96, max_connections: 100 },
  },
  {
    type: 'error_spike',
    severity: 'critical',
    service: 'checkout-web',
    message: 'Checkout conversion dropped 18% while orders-api returns HTTP 500.',
    error_rate: 40,
    metadata: { environment: 'demo', dependency: 'orders-api' },
  },
];

/**
 * Emulates the dashboard SSE feed: connects immediately, then emits periodic
 * keepalives and new alerts. `track` receives a disposer for every timer so the
 * caller can tear the whole stream down.
 */
export function demoStream(
  path: string,
  handlers: DemoStreamHandlers,
  track: (dispose: () => void) => void,
): void {
  const normalized = path.replace(/\/+$/, '');

  const openTimer = setTimeout(() => {
    handlers.onOpen?.();
    handlers.onMessage?.(JSON.stringify({ type: 'connected', stream: 'dashboard', demo: true }));
  }, 200);
  track(() => clearTimeout(openTimer));

  if (normalized !== '/dashboard/stream') {
    const unsupported = setTimeout(
      () => handlers.onError?.(),
      200,
    );
    track(() => clearTimeout(unsupported));
    return;
  }

  let index = 0;
  const ping = setInterval(() => {
    handlers.onMessage?.(JSON.stringify({ type: 'ping' }));
  }, 15000);
  track(() => clearInterval(ping));

  const alerts = setInterval(() => {
    const template = LIVE_ALERTS[index % LIVE_ALERTS.length];
    index += 1;
    handlers.onMessage?.(
      JSON.stringify({
        type: 'alert',
        data: { ...template, id: randomId('evt_demo_live'), timestamp: new Date().toISOString() },
      }),
    );
  }, 22000);
  track(() => clearInterval(alerts));
}
