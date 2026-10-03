# DevRelAgent

> 24/7 AI-Powered Developer Relations Agent — Combines RAG, observability, code intelligence, browser automation, and a Known Error Database to supercharge developer support.

## CLI Usage

The DevRelAgent CLI provides production-grade command-line interface with multiple flags for different use cases:

### Basic Investigation

```bash
# Run an investigation
python cli.py investigate "Why is the API slow?"

# Dry-run mode (no write operations)
python cli.py investigate "API errors" --dry-run

# JSON output for automation
python cli.py investigate "Database latency" --json

# Auto-approve all actions (use with caution)
python cli.py investigate "Create dashboard" --auto-approve
```

### Advanced CLI Flags

```bash
# Verbose mode with detailed output
python cli.py investigate "API errors" --verbose

# Use specific session ID for continuity
python cli.py investigate "Follow up on previous issue" --session sess_20260311_120000

# Combined flags
python cli.py investigate "Check logs" --dry-run --verbose --json

# Status and monitoring
python cli.py status --verbose
python cli.py list-investigations --status completed --limit 10

# Export audit logs
python cli.py export-audit --output audit.json
```

### CLI Flag Reference

| Flag | Description | Example |
|------|-------------|---------|
| `--dry-run` | Show what would be done without executing | `--dry-run` |
| `--json` | Output results in JSON format | `--json` |
| `--auto-approve` | Skip approval prompts (use with caution) | `--auto-approve` |
| `--session` | Specify session ID for continuity | `--session sess_123` |
| `--verbose, -v` | Increase output verbosity | `--verbose` |
| `--debug` | Enable debug logging | `--debug` |

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                    │
└────────────────────────┬────────────────────────────────┘
                         │ REST / SSE
┌────────────────────────▼────────────────────────────────┐
│                  FastAPI Backend                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │  Agent    │  │  Guard-  │  │    Tool Registry      │  │
│  │  Loop     │→ │  rails   │→ │ ┌──────┐ ┌────────┐  │  │
│  │ P→R→M→A  │  │ I/O/Tool │  │ │ Code │ │  Doc   │  │  │
│  └──────────┘  └──────────┘  │ │Search│ │ Search │  │  │
│                              │ └──────┘ └────────┘  │  │
│  ┌──────────┐  ┌──────────┐  │ ┌──────┐ ┌────────┐  │  │
│  │  Memory   │  │  Skills  │  │ │ MCP  │ │Browser │  │  │
│  │ Conv/KeDB │  │ Compose  │  │ │Server│ │  Use   │  │  │
│  └──────────┘  └──────────┘  │ └──────┘ └────────┘  │  │
│                              └──────────────────────┘  │
└────────────────────────┬────────────────────────────────┘
                         │
        ┌────────────────┼────────────────┐
        ▼                ▼                ▼
   ┌─────────┐    ┌───────────┐    ┌───────────┐
   │  FAISS  │    │ ClickHouse│    │ GitHub /  │
   │ Vectors │    │   Logs    │    │ GitLab API│
   └─────────┘    └───────────┘    └───────────┘
```

**Cognitive Pipeline**: Perception → Routing → Memory → Action

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Anthropic Claude (default), OpenAI, Google Gemini — swappable |
| Embeddings | Ollama nomic-embed-text (local) |
| Vector DB | FAISS |
| Code Parsing | tree-sitter (Python, JS, TS, Java, Rust, Go, C/C++, Ruby) |
| Backend | FastAPI + Pydantic |
| Tool Protocol | MCP (Model Context Protocol) |
| Frontend | Next.js (Phase 3) |

## Quick Start

```bash
# 1. Clone and setup
git clone <repo-url>
cd DevRelAgent
python3 -m venv .venv && source .venv/bin/activate
pip install -e "."

# 2. Configure
cp .env.example .env
# Edit .env with your API keys

# 3. Start Ollama (for embeddings)
ollama serve &
ollama pull nomic-embed-text

# 4. Run
python apps/backend/main.py
# → http://localhost:8000/health
```

## Project Structure

```
DevRelAgent/
├── apps/backend/
│   ├── main.py                    # FastAPI entry point
│   ├── agent/
│   │   ├── llm_provider.py        # Multi-LLM abstraction
│   │   ├── loop.py                # Agent cognitive pipeline
│   │   ├── router.py              # Intent classification
│   │   └── planner.py             # Multi-step ReAct planner
│   ├── models/
│   │   └── schemas.py             # All Pydantic models
│   ├── tools/
│   │   ├── registry.py            # Tool registration
│   │   ├── code_search/           # ★ Git repo indexing
│   │   │   ├── code_chunker.py    # AST parsing + text fallback
│   │   │   ├── vector_store.py    # FAISS + embeddings
│   │   │   ├── mcp_server.py      # 8 MCP tools
│   │   │   └── config.py          # Settings
│   │   └── doc_search/            # Document indexing (team)
│   │       ├── base.py            # Abstract DocumentIndexer
│   │       └── README.md          # Implementation guide
│   ├── guardrails/                # Input/Output/Tool guards
│   ├── memory/                    # Conversation + KeDB
│   ├── mcp/                       # Unified MCP server
│   └── skills/                    # Composable workflows
├── data/                          # Repos, indexes, KeDB
├── tests/                         # Verification tests
├── scripts/                       # Ingestion scripts
└── pyproject.toml                 # Dependencies
```

## Code Search MCP Tools

The code search module exposes 8 tools via MCP:

| Tool | Description |
|------|-------------|
| `clone_repository` | Clone a GitHub repo locally |
| `index_repository` | Parse code → AST chunks → FAISS embeddings |
| `search_code` | Natural language semantic code search |
| `get_file_content` | Read file with line numbers |
| `list_files` | Glob-based file listing |
| `get_repo_status` | Current repo info and index status |
| `load_repository` | Switch to a previously indexed repo |
| `list_indexed_repos` | List all cloned/indexed repos |

## Multi-LLM Support

Switch providers via `.env`:

```bash
LLM_PROVIDER=anthropic   # or: openai, gemini
LLM_MODEL=claude-haiku-4-5-20251001  # or: gpt-4o-mini, gemini-2.0-flash
```

## Running Tests

```bash
source .venv/bin/activate
python tests/test_code_search.py
```

## Roadmap

- [x] **Phase 1**: Skeleton + Code Search + RAG foundation
- [ ] **Phase 2**: MCP Server + Skills + ClickHouse SQL + Output Guardrails
- [ ] **Phase 3**: KeDB + Self-Correction + HITL + Frontend
- [ ] **Phase 4**: Browser Use + Multi-step Reasoning + Polish

## Reference

- [CodeRepoSemanticSearch](./CodeRepoSemanticSearch/) — Reference implementation for code indexing
- [ProjectPlan.md](./ProjectPlan.md) — Full project proposal and architecture
- [Issues.md](./Issues.md) — Detailed issue breakdown by phase

## Documentation

> **Project status: active development / prototype.** The API now requires an
> identity and is scoped to a workspace and project (Phase 1), but the default
> `AUTH_PROVIDER=dev` trusts caller-supplied headers and must **not** be exposed
> to an untrusted network. Switch to Clerk (or another OIDC provider) for any
> real deployment.

### Security & Governance

- **[Security Model](./docs/security.md)** - Security architecture, implemented controls, and threat mitigation
- **[Capabilities](./docs/capabilities.md)** - What DevRelAgent can and cannot do, risk levels, and usage guidelines
- **[Disabling](./docs/disable.md)** - How to disable or shut down DevRelAgent in various scenarios

### Operational Documentation

- **[Incident Scenarios](./docs/incidents.md)** - Real-world incident examples and how DevRelAgent helps resolve them
- **[Audit Trail](./apps/backend/audit/)** - Audit logging for security and traceability
- **[Guardrails](./apps/backend/guardrails/)** - Input/output/tool validation and approval workflows

### Key Features

#### **Audit Trail**
- Logging of user interactions and tool executions
- Append-only JSONL audit files (content hashing / tamper evidence is not yet implemented)
- Export capabilities (JSON/CSV) for reporting
- Approval history

#### **Security Controls**
- Multi-layer guardrails (input, output, tool)
- Intent classification with confidence scoring
- Human-in-the-loop approval for risky actions
- PII detection and redaction

#### **Explain-Before-Act**
- Detailed explanations before tool execution
- Risk assessment and expected outcomes
- Approval request generation for high-risk actions

#### **Structured Outputs**
- Confidence scores and certainty levels
- Evidence-backed observations
- Actionable recommendations
- Next steps and suggested actions

### Identity & Multi-Tenancy (Phase 1)

Every request resolves to a **Workspace → Project** scope, and data access is
confined to it.

- **Workspaces and projects** live in the backend's own system of record
  (SQLite by default; point `DATABASE_URL` at Postgres/Supabase for real use).
- **Users** join workspaces through memberships with a role
  (`owner`, `admin`, `member`, `viewer`). The creator of a workspace owns it.
- **Identity providers** are pluggable. `AUTH_PROVIDER=dev` derives the caller
  from `X-Dev-User-Email` / `X-Dev-User-Name` / `X-Dev-Workspace` headers (and
  the matching query parameters, which is how the browser `EventSource` streams
  identify themselves). `AUTH_PROVIDER=clerk` verifies a real Clerk/OIDC JWT
  against the issuer's JWKS.
- **Projects** are selected with `X-Project-Id` / `X-Project-Slug` (or
  `?project_id=`); requests without one use the workspace's default project.
- **Project API keys** (`drk_<prefix>_<secret>`) authenticate machine access.
  Only a salted hash is stored. Keys can read data-plane endpoints but cannot
  administer workspaces.
- **Migrations** are managed by Alembic: `cd apps/backend && alembic upgrade head`.
  Set `DATABASE_AUTO_CREATE=false` in production.
- **Sessions** are shared through a pluggable store (`SESSION_BACKEND=memory` for
  a single process, `redis` for multiple replicas).
- **Audit trail and approvals** are persisted in the system of record and scoped
  to a project, so history survives restarts and never leaks across tenants.
  Audit entries are additionally hash-chained per project, so any edit,
  deletion or reordering of a stored entry is detectable via
  `GET /audit/verify`.
- **Guardrail and limit state** (rate-limit windows, token budgets, circuit
  breakers) lives in a shared state backend (`SESSION_BACKEND=redis`) and is
  scoped per project, so every replica enforces the same limits.
- **Edge rate limiting** puts a coarse, per-project/identity request budget in
  front of every endpoint, shared across replicas, returning `429` with a
  `Retry-After` header when exceeded.
- **Observability** assigns a request id and W3C `traceparent` to every request
  (echoed back in the response headers and included in the JSON logs), records
  HTTP latency/summary metrics, and exposes them in Prometheus text format at
  `GET /metrics`.

Endpoints: `GET /auth/me`, `GET/POST /workspaces`, `GET /workspaces/current/members`,
`GET/POST /projects`, `PATCH /projects/{id}`, `POST /projects/{id}/archive`,
`GET/POST/DELETE /projects/{id}/api-keys`, `GET /audit/verify`, and `GET /metrics`.

**Frontend pages**: `/` (chat), `/dashboard` (live activity), `/approvals`
(review and respond to pending approvals, with recent-decision history), and
`/workspace` (workspace + members, project lifecycle, and project API keys).
Each page shares the same header, project switcher and navigation.

### Deployment Considerations

- **Multi-tenant (Phase 1)**: workspace/project isolation is enforced in the
  backend, and audit entries plus approval decisions are durable and scoped per
  project.
- **Cross-replica approvals (Phase 6)**: an approval decision recorded on any
  replica is published on a shared event bus and also polled from the system of
  record, so the process blocked on it is released even if pub/sub is down.
- **Shared limits (Phase 3)**: rate-limit windows, token budgets and circuit
  breakers are shared across replicas and scoped per project, so limits hold
  under horizontal scaling instead of being enforced independently per process.
- **Edge limiting + tamper-evident audit (Phase 4)**: every request passes a
  shared, per-project request budget, and audit entries are hash-chained per
  project so tampering is detectable. Note: the chain guards *stored* entries
  after the fact; it is not yet anchored to an external notary/witness.
- **Observability (Phase 5)**: requests are correlated by request id and W3C
  `traceparent` across replicas, logged as JSON with `request_id`/`trace_id`,
  and measured via `GET /metrics` (Prometheus format). Trace spans are held in
  memory per replica; exporting to a tracing backend is a follow-up.
- **Not certified**: DevRelAgent holds no security certification and makes no
  compliance guarantee. It implements some controls that *support* compliance
  work (PII redaction, audit logging, approval gates); certification would
  require an independent audit.
- **Scale**: the API is async and can run multiple replicas with
  `SESSION_BACKEND=redis`; sessions and guardrail/limit state are shared across
  replicas, while vector indexes remain process-local
- **Monitoring**: health and metrics endpoints are provided

### Support

For production deployments:
- **Documentation**: [Project Wiki](https://github.com/your-org/DevRelAgent/wiki)
- **Issues**: [GitHub Issues](https://github.com/your-org/DevRelAgent/issues)
- **Security**: security@example.com
- **Support**: support@example.com
