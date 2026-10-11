/**
 * Static demo dataset for the GitHub Pages showcase build.
 *
 * The real product reads this shape from the FastAPI backend. Here it is
 * checked in as fixtures so the UI can be explored without a backend, a
 * database, or any credentials. Everything is synthetic and modelled on the
 * `orders-api` pool-timeout incident that ships with the repository
 * (`scripts/fixtures/demo_incident.jsonl`).
 *
 * Timestamps are generated relative to "now" each time the page loads so the
 * relative labels ("2m ago", "Live") stay meaningful on a static host.
 */

import type {
  ApprovalHistory,
  ApprovalRequest,
  ApiKey,
  Member,
  Project,
  Workspace,
} from './types';

export interface DemoAlert {
  id: string;
  type: 'alert' | 'health_check' | 'error_spike';
  severity: 'critical' | 'warning' | 'info';
  service: string;
  message: string;
  error_rate?: number;
  timestamp: string;
  metadata?: Record<string, unknown>;
}

export interface DemoState {
  workspace: Workspace;
  members: Member[];
  projects: Project[];
  apiKeys: Record<string, ApiKey[]>;
  alerts: DemoAlert[];
  services: Record<string, 'green' | 'yellow' | 'red'>;
  servicesMonitoredAt: string;
  pending: ApprovalRequest[];
  history: ApprovalHistory['history'];
}

const MINUTE = 60 * 1000;

function iso(now: number, minutesAgo: number): string {
  return new Date(now - minutesAgo * MINUTE).toISOString();
}

/** Fresh, mutable demo state. `now` is injectable to keep tests deterministic. */
export function createDemoState(now: number = Date.now()): DemoState {
  return {
    workspace: {
      id: 'ws_demo_devrel',
      name: 'DevRel Engineering',
      slug: 'dev-workspace',
      external_id: null,
      created_at: iso(now, 240 * 24 * 60),
      role: 'owner',
    },
    members: [
      { user_id: 'usr_demo_dev', email: 'dev@localhost', name: 'Dev User', role: 'owner' },
      { user_id: 'usr_demo_priya', email: 'priya@example.com', name: 'Priya Raman', role: 'admin' },
      { user_id: 'usr_demo_marco', email: 'marco@example.com', name: 'Marco Silva', role: 'member' },
      { user_id: 'usr_demo_sam', email: 'sam@example.com', name: 'Sam Okafor', role: 'viewer' },
    ],
    projects: [
      {
        id: 'prj_orders_platform',
        workspace_id: 'ws_demo_devrel',
        name: 'Orders Platform',
        slug: 'orders-platform',
        description: 'Checkout, orders and payment orchestration services.',
        status: 'active',
        created_at: iso(now, 240 * 24 * 60),
        archived_at: null,
      },
      {
        id: 'prj_core_platform',
        workspace_id: 'ws_demo_devrel',
        name: 'Core Platform',
        slug: 'core-platform',
        description: 'Shared services: identity, notifications and search.',
        status: 'active',
        created_at: iso(now, 210 * 24 * 60),
        archived_at: null,
      },
      {
        id: 'prj_legacy_billing',
        workspace_id: 'ws_demo_devrel',
        name: 'Legacy Billing',
        slug: 'legacy-billing',
        description: 'Deprecated billing service, kept read-only for historic logs.',
        status: 'archived',
        created_at: iso(now, 400 * 24 * 60),
        archived_at: iso(now, 72 * 24 * 60),
      },
    ],
    apiKeys: {
      prj_orders_platform: [
        {
          id: 'key_demo_ci',
          name: 'ci-pipeline',
          prefix: 'drk_live_c1a4',
          scopes: ['read:logs', 'read:traces'],
          created_at: iso(now, 60 * 24 * 60),
          last_used_at: iso(now, 12),
          expires_at: null,
          revoked_at: null,
        },
        {
          id: 'key_demo_grafana',
          name: 'grafana-bridge',
          prefix: 'drk_live_9f2b',
          scopes: ['read:logs'],
          created_at: iso(now, 120 * 24 * 60),
          last_used_at: iso(now, 60 * 24 * 3),
          expires_at: null,
          revoked_at: iso(now, 30 * 24 * 60),
        },
      ],
      prj_core_platform: [
        {
          id: 'key_demo_incident_bot',
          name: 'incident-bot',
          prefix: 'drk_live_77de',
          scopes: ['read:logs', 'read:docs'],
          created_at: iso(now, 30 * 24 * 60),
          last_used_at: iso(now, 45),
          expires_at: null,
          revoked_at: null,
        },
      ],
    },
    alerts: [
      {
        id: 'evt_demo_0001',
        type: 'error_spike',
        severity: 'critical',
        service: 'orders-api',
        message:
          'Connection pool timeout after each checkout attempt (3 failures in 4 minutes, HTTP 500 on POST /v1/orders).',
        error_rate: 40,
        timestamp: iso(now, 2),
        metadata: {
          environment: 'demo',
          deployment_version: '2026.10.05-02',
          trace_id: '30000000000000000000000000000001',
          diagnosis: {
            likely_cause: 'database connection pool exhaustion',
            evidence: [
              'child postgres client span waits 5s then errors',
              'pool_wait_ms rose from 4ms to 5000ms after deploy',
            ],
            suggested_action: 'restart orders-api or roll back deployment 2026.10.05-02',
          },
        },
      },
      {
        id: 'evt_demo_0002',
        type: 'alert',
        severity: 'warning',
        service: 'inventory-api',
        message: 'Upstream calls timing out at 5s (HTTP 503) since deployment 2026.10.05-02.',
        error_rate: 12.5,
        timestamp: iso(now, 6),
        metadata: { environment: 'demo', dependency: 'postgres-primary' },
      },
      {
        id: 'evt_demo_0003',
        type: 'alert',
        severity: 'warning',
        service: 'search-api',
        message: 'p95 query latency 1.4s while the nightly index rebuild runs.',
        error_rate: 2.1,
        timestamp: iso(now, 14),
        metadata: { environment: 'demo', job: 'index-rebuild' },
      },
      {
        id: 'evt_demo_0004',
        type: 'health_check',
        severity: 'info',
        service: 'auth-api',
        message: 'Token refresh retry storm subsided; error rate back under threshold.',
        error_rate: 0.8,
        timestamp: iso(now, 32),
        metadata: { environment: 'demo', window_minutes: 15 },
      },
      {
        id: 'evt_demo_0005',
        type: 'alert',
        severity: 'warning',
        service: 'payments-api',
        message: 'p99 latency 1.8s on POST /v1/charges, above the 900ms objective.',
        error_rate: 4.2,
        timestamp: iso(now, 61),
        metadata: { environment: 'demo', dependency: 'stripe-gateway' },
      },
      {
        id: 'evt_demo_0006',
        type: 'health_check',
        severity: 'info',
        service: 'notifications-api',
        message: 'Queue depth recovered to baseline (12 pending messages).',
        timestamp: iso(now, 128),
        metadata: { environment: 'demo' },
      },
    ],
    services: {
      'orders-api': 'red',
      'inventory-api': 'yellow',
      'search-api': 'yellow',
      'postgres-primary': 'yellow',
      'payments-api': 'green',
      'auth-api': 'green',
      'notifications-api': 'green',
      'web-bff': 'green',
    },
    servicesMonitoredAt: iso(now, 1),
    pending: [
      {
        approval_id: 'apr_demo_0001',
        action_type: 'restart_service',
        plan: [
          'Drain traffic from the 6 orders-api replicas one at a time',
          'Restart the orders-api deployment in the production namespace',
          'Watch error rate for 5 minutes and escalate if it stays above 5%',
        ],
        risk_level: 'critical',
        metadata: {
          service: 'orders-api',
          namespace: 'production',
          replicas: 6,
          requested_by: 'devrel-agent',
          reason: 'Connection pool timeouts are failing 40% of checkout requests.',
        },
        timeout_seconds: 900,
        created_at: iso(now, 3),
      },
      {
        approval_id: 'apr_demo_0002',
        action_type: 'rollback_deployment',
        plan: [
          'Compare error rate before and after deployment 2026.10.05-02',
          'Roll orders-api back to 2026.10.04-17',
          'Post the incident summary to #orders-oncall',
        ],
        risk_level: 'high',
        metadata: {
          service: 'orders-api',
          from_version: '2026.10.05-02',
          to_version: '2026.10.04-17',
        },
        timeout_seconds: 600,
        created_at: iso(now, 8),
      },
      {
        approval_id: 'apr_demo_0003',
        action_type: 'create_dashboard',
        plan: [
          'Create a "orders-api pool health" dashboard',
          'Add pool wait time, connection saturation and HTTP 5xx panels',
          'Share it with the on-call rotation',
        ],
        risk_level: 'low',
        metadata: { dashboard: 'orders-api-pool-health', panels: 3 },
        timeout_seconds: 300,
        created_at: iso(now, 21),
      },
    ],
    history: [
      {
        approval_id: 'apr_demo_0100',
        action_type: 'query_logs',
        risk_level: 'low',
        approved: true,
        user: 'dev@localhost',
        reason: 'Read-only investigation.',
        created_at: iso(now, 40),
        responded_at: iso(now, 39),
        duration_seconds: 12,
        plan: ['Query recent ERROR rows for orders-api'],
        metadata: { service: 'orders-api' },
      },
      {
        approval_id: 'apr_demo_0101',
        action_type: 'run_incident_report',
        risk_level: 'low',
        approved: true,
        user: 'priya@example.com',
        reason: 'Needed for the postmortem doc.',
        created_at: iso(now, 95),
        responded_at: iso(now, 94),
        duration_seconds: 8,
        plan: ['Draft the incident summary from logs and traces'],
        metadata: {},
      },
      {
        approval_id: 'apr_demo_0102',
        action_type: 'delete_index',
        risk_level: 'critical',
        approved: false,
        user: 'priya@example.com',
        reason: 'Index rebuild is safer and reversible.',
        created_at: iso(now, 180),
        responded_at: iso(now, 176),
        duration_seconds: 240,
        plan: ['Drop the stale search index and rebuild from the primary store'],
        metadata: { index: 'search-v12' },
      },
      {
        approval_id: 'apr_demo_0103',
        action_type: 'scale_service',
        risk_level: 'medium',
        approved: true,
        user: 'marco@example.com',
        reason: 'Latency spike during the marketing launch.',
        created_at: iso(now, 26 * 60),
        responded_at: iso(now, 26 * 60 - 2),
        duration_seconds: 120,
        plan: ['Raise payments-api replicas from 4 to 8'],
        metadata: { service: 'payments-api' },
      },
      {
        approval_id: 'apr_demo_0104',
        action_type: 'rotate_api_key',
        risk_level: 'medium',
        approved: false,
        user: 'dev@localhost',
        reason: 'Waiting for the Grafana migration window.',
        created_at: iso(now, 30 * 60),
        responded_at: iso(now, 30 * 60 - 5),
        duration_seconds: 300,
        plan: ['Rotate the grafana-bridge project API key'],
        metadata: {},
      },
    ],
  };
}

export interface DemoChatReply {
  response: string;
  sql_executed?: string;
  tool_calls?: Array<{ tool_name: string; result: Record<string, unknown> }>;
}

interface Intent {
  keywords: string[];
  reply: () => DemoChatReply;
}

const ORDERS_SQL = [
  'SELECT timestamp, level, status_code, error_message, trace_id',
  'FROM logs.logs',
  "WHERE service = 'orders-api'",
  "  AND level = 'ERROR'",
  '  AND timestamp >= now() - INTERVAL 1 HOUR',
  'ORDER BY timestamp DESC',
  'LIMIT 20',
].join('\n');

const LATENCY_SQL = [
  'SELECT toStartOfMinute(timestamp) AS minute,',
  '       quantile(0.95)(duration_ms) AS p95_ms,',
  '       quantile(0.99)(duration_ms) AS p99_ms',
  'FROM logs.otel_metrics',
  "WHERE service_name = 'orders-api'",
  "  AND metric_name = 'http.server.duration'",
  '  AND timestamp >= now() - INTERVAL 1 HOUR',
  'GROUP BY minute',
  'ORDER BY minute',
].join('\n');

const INTENTS: Intent[] = [
  {
    keywords: ['orders-api', 'pool', 'timeout', '500', 'error', 'incident', 'trace', 'outage', 'broken'],
    reply: () => ({
      response: [
        '**orders-api has been failing checkout requests for the last 6 minutes.**',
        '',
        'What the evidence shows:',
        '',
        '1. `logs` — 3 HTTP 500 responses on `POST /v1/orders` with `context deadline exceeded` while acquiring a PostgreSQL connection.',
        '2. `otel_traces` — each failed request has a server span plus a child `postgresql` client span that waits ~5,000 ms before erroring.',
        '3. `otel_metrics` — `error_rate` 40%, request p95 5,200 ms (baseline 84–126 ms), `pool.wait_ms` 5,000 ms.',
        '',
        'All three signals begin after deployment `2026.10.05-02`, which matches the connection-pool sizing change in that release. The trace IDs line up across logs and spans, so this is not a message-only guess.',
        '',
        '**Recommended next step:** restarting `orders-api` clears the stuck pool, but rolling back `2026.10.05-02` removes the cause. Both are high-impact actions, so they are queued for human approval in the Approvals tab.',
        '',
        'Trace to pivot on: `30000000000000000000000000000001`.',
      ].join('\n'),
      sql_executed: ORDERS_SQL,
      tool_calls: [
        {
          tool_name: 'observability.get_top_errors',
          result: {
            service: 'orders-api',
            window: 'last 60m',
            total_errors: 3,
            top_error: 'context deadline exceeded: acquiring connection from pool',
          },
        },
        {
          tool_name: 'observability.correlate_trace',
          result: {
            trace_id: '30000000000000000000000000000001',
            spans: 4,
            slowest_span: 'postgresql.query (5002 ms)',
            status: 'ERROR',
          },
        },
      ],
    }),
  },
  {
    keywords: ['latency', 'slow', 'p95', 'p99', 'performance', 'duration'],
    reply: () => ({
      response: [
        '**Latency for `orders-api` is 40× the pre-deployment baseline.**',
        '',
        '| window | p95 | p99 |',
        '| --- | --- | --- |',
        '| before `2026.10.05-02` | 126 ms | 155 ms |',
        '| after `2026.10.05-02` | 5,200 ms | 5,400 ms |',
        '',
        'The step change is a plateau rather than a gradual rise, which points at a blocking wait (connection acquisition) rather than saturation. `pool.wait_ms` climbing to 5,000 ms confirms the queue is at the pool, not at the application.',
        '',
        'In a real deployment this query would run against your telemetry store; here it is served from the checked-in demo fixture.',
      ].join('\n'),
      sql_executed: LATENCY_SQL,
      tool_calls: [
        {
          tool_name: 'observability.latency_summary',
          result: { service: 'orders-api', p95_ms: 5200, baseline_p95_ms: 126, unit: 'ms' },
        },
      ],
    }),
  },
  {
    keywords: ['doc', 'documentation', 'knowledge', 'kan', 'kedb', 'how do', 'guide'],
    reply: () => ({
      response: [
        'I searched the configured knowledge sources and these are the closest matches:',
        '',
        '1. **Connection pool sizing runbook** — keep `max_connections` at or below 80% of the database limit and set `pool_timeout` to 2× p99 query time.',
        '2. **Deployment comparison checklist** — always diff `error_rate`, p95 latency and pool wait metrics before and after a release.',
        '3. **Incident response policy** — read-only queries may run automatically; restarts, rollbacks and destructive changes require an approval.',
        '',
        'Every answer cites the source document it came from, and the agent refuses to action anything the sources do not support.',
      ].join('\n'),
      tool_calls: [
        {
          tool_name: 'docs.search',
          result: {
            results: [
              { title: 'Connection pool sizing runbook', score: 0.91 },
              { title: 'Deployment comparison checklist', score: 0.84 },
              { title: 'Incident response policy', score: 0.79 },
            ],
          },
        },
      ],
    }),
  },
  {
    keywords: ['architecture', 'system', 'design', 'component', 'diagram', 'how does', 'pipeline'],
    reply: () => ({
      response: [
        'DevRelAgent is a **Perception → Routing → Memory → Action** pipeline behind a FastAPI service:',
        '',
        '- **Perception** normalises the request (message, workspace, project scope) and classifies intent with a confidence score.',
        '- **Routing** picks the tools for that intent — code search, document search, observability queries, or the browser tool.',
        '- **Memory** keeps the conversation plus the Known Error Database, and scopes both to the active project.',
        '- **Action** runs the plan behind guardrails: input/output/tool validation, PII redaction, and a human approval gate for anything high impact.',
        '',
        'The Next.js frontend you are using is the same app that ships in `apps/frontend`; only its data source is swapped for the static demo fixtures.',
      ].join('\n'),
      tool_calls: [
        {
          tool_name: 'code_search.find',
          result: {
            matches: [
              { file: 'apps/backend/agent/loop.py', symbol: 'run_pipeline' },
              { file: 'apps/backend/guardrails/input_guard.py', symbol: 'validate' },
            ],
          },
        },
      ],
    }),
  },
  {
    keywords: ['deploy', 'deployment', 'version', 'release', 'compare', 'rollback'],
    reply: () => ({
      response: [
        'Comparing the two deployments for `orders-api`:',
        '',
        '- `2026.10.04-17` (baseline): success responses 84–126 ms, error rate 0.4%.',
        '- `2026.10.05-02` (current): error rate 40%, p95 5,200 ms, `pool.wait_ms` 5,000 ms.',
        '',
        'The regression is isolated to the current release, so rolling back to `2026.10.04-17` is the fastest reversible mitigation. I have queued that rollback for approval rather than executing it.',
      ].join('\n'),
      sql_executed: [
        'SELECT deployment_version,',
        '       countIf(status_code >= 500) / count() AS error_rate,',
        '       quantile(0.95)(duration_ms) AS p95_ms',
        'FROM logs.logs',
        "WHERE service = 'orders-api'",
        'GROUP BY deployment_version',
        'ORDER BY min(timestamp)',
      ].join('\n'),
    }),
  },
  {
    keywords: ['approval', 'approve', 'guardrail', 'permission', 'risk', 'safe', 'security'],
    reply: () => ({
      response: [
        'Every action is classified by risk before it runs:',
        '',
        '- **Low** — read-only queries and report generation run immediately.',
        '- **Medium / High** — scaling, key rotation and rollbacks wait for a reviewer.',
        '- **Critical** — service restarts and destructive operations require an explicit approval, and the plan is shown before execution.',
        '',
        'There are 3 approvals waiting in the Approvals tab right now: a critical `restart_service`, a high-risk `rollback_deployment`, and a low-risk `create_dashboard`. Approving or rejecting them is safe here — decisions only update this browser session\'s demo state.',
      ].join('\n'),
    }),
  },
  {
    keywords: ['log', 'metric', 'observability', 'clickhouse', 'query', 'sql', 'dashboard'],
    reply: () => ({
      response: [
        'Here is the recent-errors query I would run, plus the summary it returns:',
        '',
        '```sql',
        ORDERS_SQL,
        '```',
        '',
        'Result: 3 ERROR rows for `orders-api`, all `context deadline exceeded` while acquiring a pooled connection, all sharing the `2026.10.05-02` deployment version.',
        '',
        'On a connected deployment this SQL is executed against your ClickHouse `logs` database over HTTP and the result set is summarised with citations.',
      ].join('\n'),
      sql_executed: ORDERS_SQL,
      tool_calls: [
        {
          tool_name: 'observability.run_query',
          result: { rows: 3, service: 'orders-api', query_ms: 128 },
        },
      ],
    }),
  },
];

const FALLBACK: DemoChatReply = {
  response: [
    'You are using the **static demo build** of DevRelAgent, so answers come from a checked-in fixture instead of a live model.',
    '',
    'Ask about any of these to see the full flow:',
    '',
    '- “Show recent errors for orders-api and correlate the failure with traces.”',
    '- “What is the latency for orders-api in the last hour?”',
    '- “Compare orders-api before and after the deployment.”',
    '- “Which documentation covers connection pool sizing?”',
    '- “How does the approval guardrail work?”',
    '',
    'The Dashboard, Approvals and Workspace tabs are live too — they render the same demo dataset.',
  ].join('\n'),
};

/** Deterministic, keyword-routed stand-in for the real agent response. */
export function demoChatReply(message: string): DemoChatReply {
  const text = message.toLowerCase();
  const scored = INTENTS.map((intent) => ({
    intent,
    score: intent.keywords.reduce(
      (total, keyword) => (text.includes(keyword) ? total + 1 : total),
      0,
    ),
  })).sort((a, b) => b.score - a.score);

  return scored[0].score > 0 ? scored[0].intent.reply() : FALLBACK;
}
