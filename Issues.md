# DevRelAgent — GitHub Project Tasks

> Copy-paste these into GitHub Issues. Each section = 1 issue.
> Suggested Labels: `phase-1`, `phase-2`, `phase-3`, `phase-4`, `agent`, `backend`, `frontend`, `infra`, `security`, `docs`

---

## Milestone: Phase 1 — Foundation (Week 1)

---

### Issue #1: Project Setup & Monorepo Scaffolding
**Labels:** `phase-1`, `infra`
**Assignee:** R1, R2, R3

**Description:**
Set up the monorepo structure with backend (FastAPI) and frontend (Next.js) projects, shared configs, and CI basics.

**Tasks:**
- [ ] Create monorepo folder structure as per proposal (`apps/backend`, `apps/frontend`, `data/`, `scripts/`, `tests/`)
- [ ] Initialize FastAPI project with `main.py`, CORS config, health endpoint
- [ ] Initialize Next.js project with TypeScript
- [ ] Add `docker-compose.yml` with ClickHouse service
- [ ] Create `.env.example` with all required env vars
- [ ] Add `README.md` with setup instructions
- [ ] Verify both apps run locally

**Acceptance Criteria:**
- `docker-compose up` starts ClickHouse
- FastAPI runs on `localhost:8000` with `/health` returning 200
- Next.js runs on `localhost:3000`

---

### Issue #2: Agent Loop — Core Cognitive Pipeline
**Labels:** `phase-1`, `agent`
**Assignee:** R1

**Description:**
Implement the `AgentLoop` with 4 cognitive layers: Perception → Routing → Memory → Action, using LlamaIndex.

**Tasks:**
- [ ] Create `agent/loop.py` — main agent orchestration
- [ ] Create `agent/router.py` — intent classification (doc-query vs log-query vs general)
- [ ] Implement Perception layer: parse user query, extract entities
- [ ] Implement Routing layer: classify intent, select tool(s)
- [ ] Implement Memory layer: check conversation history for context
- [ ] Implement Action layer: execute selected tool, format response
- [ ] Create `models/schemas.py` — Pydantic models for tool I/O
- [ ] Wire LlamaIndex function calling for tool selection

**Acceptance Criteria:**
- Agent correctly routes "How do I authenticate?" to RAG tool
- Agent correctly routes "Show recent errors" to ClickHouse tool
- Agent maintains conversation context within session

---

### Issue #3: RAG Tool — Documentation Search
**Labels:** `phase-1`, `agent`, `backend`
**Assignee:** R1, R2

**Description:**
Build the RAG pipeline: ingest docs → chunk → embed → FAISS index → retrieval-augmented answers.

**Tasks:**
- [ ] Create `scripts/ingest_docs.py` — doc chunking + embedding pipeline
- [ ] Create `tools/rag_tool.py` — FAISS retrieval + LLM answer generation
- [ ] Create `tools/registry.py` — tool registration framework
- [ ] Implement chunking strategy (experiment with chunk sizes 256/512/1024)
- [ ] Support Markdown and Swagger/OpenAPI doc formats
- [ ] Store FAISS index in `data/faiss_index/`
- [ ] Add source citations to generated answers
- [ ] Write unit tests for chunking and retrieval

**Acceptance Criteria:**
- Given sample docs in `data/docs/`, ingestion creates a FAISS index
- Query "How do I set up OAuth2?" returns relevant doc passage with citation
- >80% relevance on 10 manual test queries

---

### Issue #4: ClickHouse SQL Tool
**Labels:** `phase-1`, `agent`, `backend`
**Assignee:** R2

**Description:**
Build a tool that converts natural language queries into ClickHouse SQL, executes them, and returns formatted results.

**Tasks:**
- [ ] Create `tools/clickhouse_tool.py`
- [ ] Implement NL → SQL conversion using LLM with schema context
- [ ] Connect to ClickHouse via `clickhouse-connect` or HTTP interface
- [ ] Define Pydantic models for query input/output
- [ ] Format results as human-readable tables/summaries
- [ ] Enforce read-only access (SELECT only) at connection level
- [ ] Add timeout (30s max per query)
- [ ] Write unit tests with mock ClickHouse data

**Acceptance Criteria:**
- "Show recent auth errors" generates valid SQL and returns results
- Non-SELECT queries are blocked at connection level
- Queries timeout after 30 seconds

---

### Issue #5: Chat Widget — Frontend
**Labels:** `phase-1`, `frontend`
**Assignee:** R3

**Description:**
Build the chat widget UI with streaming responses, message bubbles, and SQL sandbox display.

**Tasks:**
- [ ] Create `ChatWidget.tsx` — collapsible chat interface
- [ ] Create `MessageBubble.tsx` — rich messages (text, code, tables)
- [ ] Create `SqlSandbox.tsx` — collapsible panel showing executed SQL
- [ ] Implement WebSocket/SSE streaming from backend
- [ ] Add typing indicator animation
- [ ] Style with modern dark/light theme
- [ ] Connect to FastAPI backend API
- [ ] Handle error states and reconnection

**Acceptance Criteria:**
- User can type a question and receive streamed response
- SQL queries display in collapsible sandbox
- Code snippets render with syntax highlighting

---

### Issue #6: Input Guardrails (Topic Filter + PII Scrubber)
**Labels:** `phase-1`, `security`
**Assignee:** R2

**Description:**
Implement input-level guardrails to filter off-topic queries and scrub PII before processing.

**Tasks:**
- [ ] Create `guardrails/input_guard.py`
- [ ] Topic classifier: LLM-based relevance check (on-topic / off-topic)
- [ ] PII scrubber: regex patterns for emails, IPs, API tokens, phone numbers
- [ ] Integrate as middleware in the agent pipeline (before routing)
- [ ] Log blocked/scrubbed queries for monitoring
- [ ] Write unit tests with PII samples

**Acceptance Criteria:**
- Off-topic query ("What's the weather?") is rejected with friendly message
- Email addresses, IPs, and tokens are stripped from queries before processing
- Clean queries pass through unchanged

---

## Milestone: Phase 2 — Code Intelligence + MCP (Week 2)

---

### Issue #7: Code Search Tool (GitHub/GitLab)
**Labels:** `phase-2`, `agent`, `backend`
**Assignee:** R1

**Description:**
Build a tool that indexes codebase function/class signatures and enables semantic search to map errors to source code.

**Tasks:**
- [ ] Create `tools/code_search_tool.py`
- [ ] GitHub API integration: clone/index repo (function/class signatures)
- [ ] Semantic search over indexed code using embeddings
- [ ] Support searching by error message, function name, or file path
- [ ] Scope limiter: `ALLOWED_REPOS` env var restricts accessible repos
- [ ] Cache indexed repos to avoid re-indexing
- [ ] Write unit tests

**Acceptance Criteria:**
- Given error `NullPointerException`, agent finds the source file and line
- Only repos in `ALLOWED_REPOS` are accessible
- Cached repos don't trigger re-indexing

---

### Issue #8: MCP Server — Tool Interop
**Labels:** `phase-2`, `agent`, `backend`
**Assignee:** R1

**Description:**
Expose all registered tools as MCP server endpoints so external MCP clients (Claude Desktop, Cursor, etc.) can call them.

**Tasks:**
- [ ] Create `mcp/server.py` using `mcp` Python SDK
- [ ] Expose RAG tool, ClickHouse tool, and Code Search tool as MCP endpoints
- [ ] Define tool schemas (input/output) in MCP format
- [ ] Add authentication/API key for MCP access
- [ ] Test with Claude Desktop or custom MCP client
- [ ] Document MCP server setup and available tools

**Acceptance Criteria:**
- MCP server starts and advertises 3+ tools
- External MCP client can successfully call `search_docs` tool
- Tool schemas match Pydantic models

---

### Issue #9: Skills Framework + DiagnoseErrorSkill
**Labels:** `phase-2`, `agent`
**Assignee:** R1

**Description:**
Build the skills framework for composable multi-tool workflows. Implement `DiagnoseErrorSkill` as the first skill.

**Tasks:**
- [ ] Design skills interface: `Skill(name, tools, execute())`
- [ ] Create `skills/diagnose_error.py`: KeDB → Logs → Code → Summary
- [ ] Create `skills/search_docs.py`: multi-source doc search
- [ ] Integrate skills into agent routing (intent → skill selection)
- [ ] Context linking: error in logs → extract signature → search code → return file path
- [ ] Write integration tests for skill execution

**Acceptance Criteria:**
- "Why is login failing?" triggers DiagnoseErrorSkill
- Skill chains: check KeDB → query logs → search code → synthesize answer
- Each step's output feeds into the next

---

### Issue #10: Output Guardrails (SQL Safety + Grounding)
**Labels:** `phase-2`, `security`
**Assignee:** R2

**Description:**
Implement output-level guardrails for SQL safety validation and response grounding checks.

**Tasks:**
- [ ] Create `guardrails/output_guard.py`
- [ ] SQL safety: AST-parse SQL, reject `INSERT`, `UPDATE`, `DELETE`, `DROP`
- [ ] Response grounding: verify answer cites at least one source (doc, log, code)
- [ ] Integrate as post-processing step in agent pipeline
- [ ] Write unit tests with malicious SQL and ungrounded responses

**Acceptance Criteria:**
- `DROP TABLE` SQL is caught and blocked before execution
- Responses without source citations are flagged
- Valid SELECT queries pass through

---

### Issue #11: Rich Message Components — Frontend
**Labels:** `phase-2`, `frontend`
**Assignee:** R3

**Description:**
Build rich message components for displaying code snippets, log streams, and error traces in the chat UI.

**Tasks:**
- [ ] Code snippet component with syntax highlighting and file links
- [ ] Log stream view with timestamp and severity highlighting
- [ ] Error trace visualization (stack trace formatting)
- [ ] Responsive layout polish
- [ ] Loading states and skeleton screens
- [ ] Write component tests

**Acceptance Criteria:**
- Code responses show syntax-highlighted snippets with file:line links
- Log results display with color-coded severity levels
- UI is responsive on desktop and tablet

---

## Milestone: Phase 3 — Reliability + Intelligence (Week 3)

---

### Issue #12: SQL Self-Correction Loop
**Labels:** `phase-3`, `agent`
**Assignee:** R1

**Description:**
Implement auto-retry logic: when a ClickHouse SQL query fails, parse the error, rewrite the SQL, and retry (max 3 attempts).

**Tasks:**
- [ ] Add retry logic in `agent/loop.py`
- [ ] Parse ClickHouse error messages to identify the issue
- [ ] LLM-based SQL rewrite with error context
- [ ] Cap retries at 3 attempts
- [ ] Log each attempt for debugging
- [ ] Write tests with intentionally broken SQL

**Acceptance Criteria:**
- Bad SQL (wrong column name) is auto-corrected and retried
- Successfully fixes at least 2 out of 3 test cases
- Stops after 3 failed attempts with user-friendly error

---

### Issue #13: Known Error Database (KeDB)
**Labels:** `phase-3`, `agent`, `backend`
**Assignee:** R2

**Description:**
Build the KeDB: a vector store of resolved issues (error_signature → root_cause → solution) that the agent checks first.

**Tasks:**
- [ ] Create `memory/kedb_store.py` — vector store for known errors
- [ ] Create `tools/kedb_tool.py` — KeDB lookup tool
- [ ] Create `scripts/seed_kedb.py` — seed initial known errors
- [ ] Implement KeDB feedback loop: resolved issues auto-added
- [ ] Agent checks KeDB *first* before running diagnostics
- [ ] Similarity threshold tuning for KeDB matches
- [ ] Write tests with known error scenarios

**Acceptance Criteria:**
- Previously resolved error returns cached solution instantly
- New resolutions are auto-added to KeDB
- KeDB is checked before other tools run

---

### Issue #14: Human-in-the-Loop (HITL) Framework
**Labels:** `phase-3`, `agent`, `frontend`
**Assignee:** R1, R3

**Description:**
Build the HITL approval gate: agent pauses on write actions, emits a plan, and waits for user approval.

**Tasks:**
- [ ] Create `ApprovalGate` middleware in `guardrails/output_guard.py`
- [ ] Define approval-required actions (GitHub issue/PR creation, etc.)
- [ ] Create `ApprovalCard.tsx` — plan preview with Approve/Reject buttons
- [ ] WebSocket event for approval request/response
- [ ] Agent pauses execution until user responds
- [ ] Log approval/rejection decisions
- [ ] Write E2E tests for approval flow

**Acceptance Criteria:**
- Agent proposing a GitHub issue shows an approval card first
- Clicking "Approve" continues execution; "Reject" cancels
- No write action executes without explicit approval

---

### Issue #15: Proactive Health Check (Cron)
**Labels:** `phase-3`, `agent`, `backend`
**Assignee:** R2

**Description:**
Implement scheduled health checks using APScheduler: query ClickHouse for error spikes and generate reports.

**Tasks:**
- [ ] Create `scheduler/health_check.py` with APScheduler
- [ ] Implement `get_top_errors()` — query error rates from ClickHouse
- [ ] Threshold-based alerting (e.g., >5% error rate)
- [ ] Auto-run `DiagnoseErrorSkill` on detected anomalies
- [ ] Post results to "The Deck" dashboard
- [ ] Configurable cron schedule via env var
- [ ] Write tests with mock ClickHouse data

**Acceptance Criteria:**
- Health check runs on configured schedule
- Error spike >5% triggers automatic diagnosis
- Results appear in The Deck dashboard feed

---

### Issue #16: The Deck — Health Dashboard
**Labels:** `phase-3`, `frontend`
**Assignee:** R3

**Description:**
Build "The Deck" — a real-time health dashboard showing alert cards, system status, and proactive insights.

**Tasks:**
- [ ] Create `DeckFeed.tsx` — scrollable feed of health events
- [ ] Alert card component (severity, service, message, timestamp)
- [ ] System status overview (green/yellow/red per service)
- [ ] Real-time updates via WebSocket/SSE
- [ ] "Click to investigate" — links alert to chat for deep-dive
- [ ] Dark mode + responsive layout
- [ ] Create `pages/index.tsx` as The Deck landing page

**Acceptance Criteria:**
- Dashboard shows live health feed with alert cards
- Clicking an alert opens chat with pre-filled investigation query
- Real-time updates without page refresh

---

### Issue #17: Tool Guardrails (Rate Limit + Timeout + Scope)
**Labels:** `phase-3`, `security`
**Assignee:** R2

**Description:**
Add tool-level guardrails: rate limiting, execution timeouts, and scope restrictions.

**Tasks:**
- [ ] Create `guardrails/tool_guard.py`
- [ ] Rate limiter: max 10 tool calls per conversation
- [ ] Timeout wrapper: 30s max per tool execution
- [ ] Scope limiter: `ALLOWED_REPOS` for GitHub, `ALLOWED_TABLES` for ClickHouse
- [ ] Integrate as decorator/wrapper on all tools
- [ ] Write tests for each guardrail

**Acceptance Criteria:**
- 11th tool call in a conversation is blocked
- Tool running >30s is terminated with timeout error
- Access to non-allowed repo/table is denied

---

## Milestone: Phase 4 — Reasoning + Browser Use + Polish (Week 4)

---

### Issue #18: Browser Use Tool (Playwright + browser-use)
**Labels:** `phase-4`, `agent`
**Assignee:** R1

**Description:**
Integrate `browser-use` + Playwright so the agent can navigate web UIs (Grafana, admin panels) and perform actions via chat commands.

**Tasks:**
- [ ] Create `tools/browser_tool.py`
- [ ] Integrate `browser-use` library with Playwright
- [ ] Implement actions: navigate, click, fill form, screenshot
- [ ] `ALLOWED_URLS` whitelist — restrict to configured domains only
- [ ] Break complex requests into step-by-step UI plans
- [ ] Stream screenshots to frontend during execution
- [ ] Mandatory HITL approval before any browser action
- [ ] Write tests against a local test page

**Acceptance Criteria:**
- "Create a dashboard in Grafana" generates a step plan
- User approves → agent executes steps with live screenshots
- Only whitelisted URLs are accessible

---

### Issue #19: Browser Session Viewer — Frontend
**Labels:** `phase-4`, `frontend`
**Assignee:** R3

**Description:**
Build the UI for viewing the agent's browser actions: live screenshot stream and HITL approval for UI actions.

**Tasks:**
- [ ] Browser session viewer component (screenshot carousel/stream)
- [ ] Step-by-step plan display with progress indicator
- [ ] HITL approval card for browser action plans
- [ ] Screenshot gallery of completed actions
- [ ] Error state handling (browser action failed)

**Acceptance Criteria:**
- User sees live screenshots as agent navigates
- Each browser plan requires approval before execution
- Completed actions show a screenshot summary

---

### Issue #20: Multi-Step Reasoning (Chain of Thought)
**Labels:** `phase-4`, `agent`
**Assignee:** R1

**Description:**
Implement multi-step reasoning for complex cross-domain queries using Chain of Thought and a correlation engine.

**Tasks:**
- [ ] Create `agent/planner.py` — ReAct-style multi-step planner
- [ ] Correlation engine: cross-reference metrics, logs, and traces
- [ ] Chain of Thought prompting for complex queries
- [ ] Step-by-step reasoning visible to user (expandable in UI)
- [ ] Write tests with complex multi-domain queries

**Acceptance Criteria:**
- Complex query triggers multi-step plan (visible to user)
- Agent cross-references logs + metrics + code in single answer
- Reasoning steps are traceable

---

### Issue #21: GitHub Issue & PR Drafting Tools
**Labels:** `phase-4`, `agent`, `backend`
**Assignee:** R2

**Description:**
Build tools to draft GitHub issues and PRs based on agent analysis, gated by HITL approval.

**Tasks:**
- [ ] Create `tools/github_tool.py`
- [ ] `draft_github_issue` — generate issue title, body, labels from analysis
- [ ] `draft_pr` — create branch, commit fix, open PR
- [ ] Preview in approval card before creation
- [ ] GitHub API integration with proper auth
- [ ] Write tests with mock GitHub API

**Acceptance Criteria:**
- Agent analysis generates a well-formatted issue draft
- User approval creates the actual GitHub issue
- PR tool creates branch + commit + PR

---

### Issue #22: Security Audit & Testing
**Labels:** `phase-4`, `security`
**Assignee:** All

**Description:**
Comprehensive security testing across all guardrails and attack surfaces.

**Tasks:**
- [ ] Prompt injection test suite (20+ attack patterns)
- [ ] PII leakage test: 50 conversations, verify zero leaks
- [ ] SQL injection test suite against ClickHouse tool
- [ ] Browser action safety: verify ALLOWED_URLS enforcement
- [ ] HITL bypass attempts: verify no write action without approval
- [ ] Rate limit enforcement under concurrent load
- [ ] Document all findings and fixes

**Acceptance Criteria:**
- Zero PII leakage in 50 test conversations
- All SQL injection attempts blocked
- No browser access outside whitelist
- No write action without HITL approval

---

### Issue #23: End-to-End Demo & Documentation
**Labels:** `phase-4`, `docs`
**Assignee:** All

**Description:**
Prepare the 5-minute live demo, record it, and finalize all documentation.

**Tasks:**
- [ ] Prepare demo script covering all 6 demo scenarios from proposal
- [ ] Set up demo data (docs, ClickHouse logs, KeDB entries, Grafana)
- [ ] Record demo video
- [ ] Create landing page with architecture diagram
- [ ] Write concepts-to-code mapping document (learning artifact)
- [ ] Final README with setup, usage, and architecture docs
- [ ] Dark mode + micro-animation polish pass

**Acceptance Criteria:**
- 5-minute demo completes all 6 scenarios without failure
- Documentation covers setup, usage, architecture, and concepts
- Landing page is deployed and presentable
