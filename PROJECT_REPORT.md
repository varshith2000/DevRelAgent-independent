# DevRelAgent — Project Guide & Implementation Report

**DevRelAgent** is a self-hosted developer-support assistant prototype. It combines a Next.js web application with a FastAPI agent backend, workspace/project scoping, configurable language-model and engineering-data integrations, approval workflows, audit records, and operations endpoints.

This guide describes what is present in the repository today, how the parts fit together, how to start a local instance, and what must be configured before expecting a capability to work. **A feature appearing in the interface or roadmap does not mean its provider, credentials, or data have been configured.**

## In plain language

A developer asks an engineering question—such as where an API is implemented, how an endpoint is configured, or what a service error might mean. The backend checks the request, routes it through the agent, and may call an available tool. It returns a response and records relevant activity. A human can review supported approval-gated actions in the approvals page.

DevRelAgent is intended to make it easier to work across engineering context. It is **not** a replacement for a production incident process, an authoritative source of truth, a security control, or a certified support service. Verify important findings with the original source.

## What is included

### User interface

- A first-run, three-step welcome and setup walkthrough at `/`.
- Chat interface with browser-local conversation history.
- **The Deck** dashboard (`/dashboard`) for service status and an activity/alert feed.
- Approvals inbox (`/approvals`) with pending decisions and recent decision history.
- Workspace admin (`/workspace`) with current workspace, members, projects, and project API-key management for permitted roles.
- Workspace/project selectors shared across application pages.
- This report is linked from the onboarding and app navigation.

The setup flow saves the development identity/workspace profile in the current browser, can check API reachability and the resolved workspace, and explains which integrations need server-side setup. It is introductory provisioning and **is not a sign-in or production identity-management system**.

### Backend and agent

The backend is a FastAPI service. Its main chat route sends messages to the agent loop, which runs input checks, intent classification, tool routing/execution when a registered tool is available, and response validation. The exact outcome depends on the active provider, installed/registered tools, credentials, indexes, and data sources.

The repository includes integrations and/or modules for multiple language-model providers, code search, document search/indexing, ClickHouse observability queries, Grafana-related tooling, GitHub-related tools, and browser automation. Some modules are optional, runtime-registered, or require external setup; verify availability in the backend configuration and logs before relying on them.

### Workspace, audit, and operations

- Requests from human identities resolve to a workspace and project; the development frontend attaches the chosen context to API calls.
- SQLite is the zero-infrastructure local system of record by default. PostgreSQL can be configured.
- Sessions use memory by default; Redis is available for shared session/guardrail state across replicas.
- Approval state and decisions are persisted and project-scoped; the cross-process notification path includes a shared event bus plus polling.
- Audit entries are persisted/scoped and hash-chained per project, with an audit-chain verification endpoint.
- Request/trace context, structured logging, HTTP metrics, and a Prometheus-compatible `/metrics` endpoint support operations.
- HTTP and tool/guardrail limits are configurable; actual production suitability still depends on deployment configuration and review.

## How the application fits together

```text
Browser (Next.js)
  ├─ onboarding, chat, dashboard, approvals, workspace admin
  ├─ development identity + selected project headers
  └─ REST requests / server-sent event streams
             │
             ▼
FastAPI backend
  ├─ identity and workspace/project resolution
  ├─ agent loop: input guard → intent/router → available tools → response checks
  ├─ approvals and audit trail
  └─ metrics, health, structured logs, trace/request identifiers
             │
             ├─ LLM provider (required for agent responses)
             ├─ optional ClickHouse / Grafana / GitHub integrations
             ├─ optional indexed documentation and code repositories
             └─ SQLite or PostgreSQL; memory or Redis session/state backend
```

## First-run setup

### Prerequisites

- Python 3.11 or later.
- Node.js 20 or later for the frontend.
- An API key for the selected LLM provider if you want the agent to produce responses. The backend validates this on startup.
- Docker Compose only if you choose the repository's optional ClickHouse/Grafana/OTel stack.

### Start the backend

From the repository root, create a Python environment, install the project and development dependencies, then copy the backend template and configure a provider:

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux:       source .venv/bin/activate
python -m pip install -e ".[dev]"
```

Copy `apps/backend/.env.example` to `apps/backend/.env`. Select one provider and provide its corresponding key:

```dotenv
LLM_PROVIDER=anthropic
LLM_MODEL=claude-haiku-4-5-20251001
ANTHROPIC_API_KEY=your-provider-key
```

The supported provider names and key variables are listed in the environment template. Keep secrets in the backend environment or a proper secret manager; **never add keys to frontend environment variables or browser code**. SQLite and in-memory sessions are the local defaults.

Run the backend from the repository root:

```bash
python apps/backend/main.py
```

Check `http://localhost:8000/health` and `http://localhost:8000/docs`.

### Start the frontend

In another terminal:

```bash
cd apps/frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. Set `NEXT_PUBLIC_API_URL` in `apps/frontend/.env.local` if the backend is not at `http://localhost:8000`; see `apps/frontend/.env.example`.

Complete the welcome walkthrough and use **Verify connection** to check the backend and workspace endpoints. A successful API check confirms reachability and workspace resolution only—it does not prove that an LLM key, ClickHouse, indexed repository, or optional integration is ready.

### Optional observability stack

`docker-compose.yml` describes additional services such as ClickHouse, Grafana, an OpenTelemetry Collector, PostgreSQL, and Redis. Those services require Docker and their own configuration. Follow [`docs/QUICK_START.md`](docs/QUICK_START.md) and review [`apps/backend/.env.example`](apps/backend/.env.example) before enabling them. The compose profile is not necessary to run the basic local UI/API setup.

## How to use the app

1. **Complete setup.** Choose a development display name, email, and workspace slug. These values are browser-local development identity values, not a user account.
2. **Check backend connectivity.** A failed check usually means the API is stopped, `NEXT_PUBLIC_API_URL` is wrong, or cross-origin access is not allowed by the backend.
3. **Ask a focused engineering question.** Include the service, endpoint, error text, time window, or repository context that will help the configured tools.
4. **Review the answer.** Tool selection and data availability depend on backend registration and configured integrations. Cross-check high-impact conclusions.
5. **Review approvals.** If a supported action creates an approval, inspect the requested action, plan, risk classification, and context before approving or rejecting it.
6. **Manage projects and keys.** Workspace permissions are enforced by the backend. Plaintext project API keys are shown only on creation; copy them into a secure secret store and revoke unused keys.

## Capabilities and dependencies

| Capability | Included in repository | What must also be true |
|---|---|---|
| Chat and agent responses | Chat route and agent orchestration | Backend starts successfully and a supported LLM provider/key is configured |
| Workspace/project identity | Backend identity, memberships, project APIs; local browser setup form | The local UI identity runs only with development auth. Real sign-in needs trusted OIDC/Clerk configuration and frontend sign-in integration |
| Code search | Code-search modules and MCP tools | A repository must be cloned/indexed and embedding/model requirements met |
| Documentation search | Document-indexer and RAG modules | Documentation must be ingested/indexed; package/module registration must be available |
| Logs/observability analysis | ClickHouse and observability tools | ClickHouse endpoint, credentials, schema/data, and the corresponding tool registration must be ready |
| Grafana operations | Grafana tooling | A reachable Grafana instance, datasource, API token, and any relevant approval configuration |
| GitHub actions | GitHub search/draft tooling | Appropriate token, repository access, and approval path for write-like actions |
| Live activity and health | Dashboard endpoints, scheduler, feed and system status UI | Scheduler and datasource configuration are optional; an empty feed or empty status map is possible without them |
| Human approvals | Approval routes, persistence, inbox UI | The particular tool/action must be registered and routed through the approval guard |
| File attachments in chat | Browser-side file selection UI | The current frontend does **not** upload file bytes or extract document contents; attachment names are only noted in the request. Do not use this control to submit secrets or expect file analysis |

## Identity and security notes

- The default `AUTH_PROVIDER=dev` trusts caller-supplied development headers. A user can edit these in browser developer tools; they do not establish a secure identity. **Never expose development auth to an untrusted network.**
- The first-run profile uses local storage and is not shared across browsers. It does not create credentials or provide authentication.
- For a real deployment, configure a supported, trusted OIDC identity provider, implement the corresponding frontend sign-in/token flow, restrict CORS and network access, and use TLS.
- Use a strong `API_KEY_PEPPER` in any real environment. The template's example values are for local development only.
- Approval gates, input checks, audit logging, and hash chains are safeguards, not guarantees that every request or action is safe or correct. The audit chain is not externally witnessed or certified.
- Do not paste secrets, private customer data, or production credentials into prompts. Check provider/data retention policies.
- DevRelAgent makes no SOC 2, HIPAA, GDPR, PCI DSS, or other certification/compliance claim. Read [`docs/security.md`](docs/security.md), [`docs/capabilities.md`](docs/capabilities.md), and [`docs/disable.md`](docs/disable.md) before deployment.

## Known limitations and follow-up work

- The frontend stores conversation displays in browser local storage. It does not restore the full backend session transcript on reload; the backend session has its own configured TTL/store. Clearing site storage removes the local display history.
- Browser-selected attachments do not reach backend tools as file bytes and are not analyzed. The UI should be treated as file-name selection only until an authenticated upload/extraction flow is implemented.
- The current development identity flow is not production authentication and onboarding is per-browser.
- A successful `/health` response reports backend/API health, not readiness of all external services. Optional integrations may be absent or unavailable.
- Some older docs, roadmap status, and comments elsewhere in the repository may describe aspirational features or older security behavior. Check live routes, current config, and tests rather than relying on all older copy.
- This report is a user-facing map, not a formal security review, operational SLO, or exhaustive API reference.

## Verification for maintainers

From `apps/frontend`, `npm run build` performs the production frontend build; `npx --no-install tsc --noEmit` performs a TypeScript check. From the repository root, the ordinary backend suite used by this checkout is:

```bash
.venv/Scripts/python.exe -m pytest -m "not integration" -q
```

On macOS/Linux, use the Python interpreter from the active virtual environment instead. Integration tests are separated by the project's pytest marker and may require external services; run them only against an appropriate local/test environment.

## Further reading

- [`README.md`](README.md) — repository overview and architecture
- [`docs/QUICK_START.md`](docs/QUICK_START.md) — optional observability setup
- [`docs/capabilities.md`](docs/capabilities.md) — capability boundaries
- [`docs/security.md`](docs/security.md) — security model and known gaps
- [`docs/incidents.md`](docs/incidents.md) — illustrative incident scenarios
- [`apps/backend/.env.example`](apps/backend/.env.example) — backend configuration template
- [`apps/frontend/.env.example`](apps/frontend/.env.example) — frontend API URL template
