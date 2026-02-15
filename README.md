# DevRelAgent — Project Proposal & Implementation Plan

> **24/7 AI-Powered Developer Relations Agent**
> Any software company plugs in their docs, codebase, and observability stack — their users get intelligent, always-on technical support.

---

## 1. Problem Statement

Developer support today is broken:

- **Docs are static** — answers are buried across pages, changelogs, and Swagger specs
- **Runtime issues need live data** — logs, traces, metrics aren't accessible to end-users
- **Code context is missing** — "is this a bug or a feature gap?" requires reading source code
- **Known errors get re-investigated** — support teams solve the same problem repeatedly
- **UI tasks still need humans** — creating dashboards, configuring alerts, or navigating admin panels requires manual clicking

**DevRelAgent** solves this by combining RAG (docs), observability (live data), code intelligence, browser automation, and a Known Error Database into a single agentic system.

---

## 2. Target User & Deployment Model

| Aspect | Detail |
|---|---|
| **Target** | Any software company with docs + observability |
| **Deployment** | Self-hosted. Company provides: docs, repo access, ClickHouse endpoint |
| **End users** | Developers using the company's software |
| **Interface** | Embeddable chat widget + health dashboard ("The Deck") |

---

## 3. Agentic AI Concepts Applied

This project is designed to cover the full spectrum of agentic AI patterns:

| Concept | Implementation | Phase |
|---|---|---|
| **RAG** | Docs/Swagger → FAISS → Context-augmented answers | 1 |
| **Tool Selection** | LLM picks from registered tools via function calling | 1 |
| **Cognitive Layers** | Perception → Routing → Memory → Action pipeline | 1 |
| **MCP** | Tools exposed as MCP servers for external client access | 2 |
| **Skills** | Composable multi-tool workflows (DiagnoseError, SearchDocs) | 2 |
| **Guardrails (Input)** | Topic classifier, PII scrubbing, prompt injection detection | 1-2 |
| **Guardrails (Output)** | SQL read-only validation, response grounding check | 2 |
| **Guardrails (Tool)** | Rate limiting, timeout, scope-limited repo access | 2 |
| **Self-Correction** | SQL repair loop (catch error → rewrite → retry ×3) | 3 |
| **Human-in-the-Loop** | Approval cards for write actions (PR, issue creation) | 3 |
| **Memory (Short-term)** | Conversation history within session | 1 |
| **Memory (Long-term)** | KeDB — resolved issues become searchable knowledge | 3 |
| **Proactive Behavior** | Cron-based health checks, anomaly detection | 3 |
| **Browser Use** | Agent navigates web UIs (Grafana, admin panels) and performs actions on behalf of the user | 4 |
| **Multi-step Reasoning** | Chain of Thought for complex cross-domain queries | 4 |

---

## 4. Architecture

```
┌───────────────────────────────────────────────────────────┐
│                      FRONTEND                            │
│  ┌──────────────────┐    ┌──────────────────────────┐     │
│  │  Chat Widget     │    │  The Deck (Dashboard)    │     │
│  │  - Rich messages │    │  - Health feed           │     │
│  │  - SQL sandbox   │    │  - Alert summaries       │     │
│  │  - Approval cards│    │  - Proactive insights    │     │
│  └────────┬─────────┘    └───────────┬──────────────┘     │
│           │         Next.js          │                    │
└───────────┼──────────────────────────┼────────────────────┘
            │         REST API         │
┌───────────┼──────────────────────────┼────────────────────┐
│           ▼       BACKEND (FastAPI)  ▼                    │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              INPUT GUARDRAILS                       │  │
│  │  Topic Classifier │ PII Scrubber │ Injection Filter │  │
│  └──────────────────────┬──────────────────────────────┘  │
│                         ▼                                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              AGENT LOOP (LlamaIndex)                │  │
│  │                                                     │  │
│  │  Perception ──► Routing ──► Memory ──► Action       │  │
│  │      │            │           │          │          │  │
│  │  Parse query   Classify    Check       Execute      │  │
│  │  + alerts      intent     KeDB/RAG     tools        │  │
│  └──────────────────────┬──────────────────────────────┘  │
│                         ▼                                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │                 TOOL REGISTRY                       │  │
│  │                                                     │  │
│  │  ┌──────────┐ ┌───────────┐ ┌────────────────────┐  │  │
│  │  │ RAG Tool │ │ ClickHouse│ │ Code Search Tool   │  │  │
│  │  │ (FAISS)  │ │ SQL Tool  │ │ (GitHub/GitLab)    │  │  │
│  │  └──────────┘ └───────────┘ └────────────────────┘  │  │
│  │  ┌──────────┐ ┌───────────┐ ┌────────────────────┐  │  │
│  │  │ KeDB     │ │ GitHub    │ │ Health Check Tool  │  │  │
│  │  │ Lookup   │ │ Issue/PR  │ │ (Cron)             │  │  │
│  │  └──────────┘ └───────────┘ └────────────────────┘  │  │
│  │  ┌──────────────────────────────────────────────┐   │  │
│  │  │ Browser Use Tool (Playwright/browser-use)    │   │  │
│  │  │ Navigate UIs, click, fill forms, screenshot  │   │  │
│  │  └──────────────────────────────────────────────┘   │  │
│  └──────────────────────┬──────────────────────────────┘  │
│                         ▼                                 │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              OUTPUT GUARDRAILS                      │  │
│  │  SQL Safety │ Grounding Check │ HITL Gate           │  │
│  └─────────────────────────────────────────────────────┘  │
│                                                           │
│  ┌─────────────────────────────────────────────────────┐  │
│  │              MCP SERVER                             │  │
│  │  Exposes tools for external MCP clients             │  │
│  │  (Claude Desktop, Cursor, custom agents)            │  │
│  └─────────────────────────────────────────────────────┘  │
└───────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────┐
│                    DATA LAYER                             │
│  ┌──────────┐  ┌────────────┐  ┌───────────────────────┐  │
│  │  FAISS   │  │ ClickHouse │  │ GitHub/GitLab API     │  │
│  │ (Vectors)│  │ (OTel Data)│  │ (Code + Issues)       │  │
│  └──────────┘  └────────────┘  └───────────────────────┘  │
└───────────────────────────────────────────────────────────┘
```

---

## 5. Tech Stack

| Layer | Technology | Reason |
|---|---|---|
| **Agent Orchestration** | LlamaIndex | Mature RAG + tool calling, Pydantic integration |
| **Data Validation** | Pydantic | Type-safe tool I/O, structured outputs |
| **Vector Store** | FAISS (local) | Fast, no infra overhead, good for MVP |
| **Backend** | FastAPI (Python) | Async, OpenAPI auto-gen, team familiarity |
| **Frontend** | Next.js (React) | SSR, component ecosystem, API routes |
| **Observability DB** | ClickHouse (ClickStack) | Team expertise, OTel native support |
| **LLM** | OpenAI GPT-4o / GPT-4o-mini | Function calling, structured output |
| **MCP** | `mcp` Python SDK | Standard protocol for tool interop |
| **Browser Automation** | `browser-use` + Playwright | LLM-driven web UI navigation and actions |
| **Scheduler** | APScheduler | Lightweight cron for health checks |

---

## 6. Team Structure (3 Resources)

| Resource | Focus Area | Phases |
|---|---|---|
| **R1 — Agent Engineer** | Agent loop, tools, LlamaIndex, MCP, Skills | All phases |
| **R2 — Backend + Data** | FastAPI, ClickHouse integration, RAG pipeline, KeDB | Phases 1-3 |
| **R3 — Frontend + UX** | Next.js, chat widget, dashboard, approval cards | Phases 1-4 |

> All 3 contribute to guardrails and testing in the final week.

---

## 7. Implementation Plan (4 Weeks)

### Phase 1 — Foundation (Week 1)
**Goal:** Agent answers questions from docs AND queries live logs.

| Day | R1 (Agent) | R2 (Backend + Data) | R3 (Frontend) |
|---|---|---|---|
| **1-2** | Project setup: monorepo, LlamaIndex skeleton, define `AgentLoop` with 4 cognitive layers | FastAPI scaffolding, ClickHouse connection, define Pydantic models for tool I/O | Next.js setup, chat widget component, WebSocket/SSE streaming |
| **3-4** | RAG tool: doc chunking → FAISS embedding → retrieval chain | ClickHouse SQL tool: natural language → SQL, execute, return results | Chat UI: message bubbles, typing indicator, SQL sandbox (collapsible) |
| **5** | Tool registry + LLM function calling (tool selection) | Input guardrail: topic classifier + PII regex scrubber | Connect chat UI to backend API, end-to-end demo |

**Phase 1 Deliverable:** User asks "How do I authenticate?" → gets doc-based answer. User asks "Show recent auth errors" → gets ClickHouse log results.

---

### Phase 2 — Code Intelligence + MCP (Week 2)
**Goal:** Agent maps errors to source code. Tools are available via MCP.

| Day | R1 (Agent) | R2 (Backend + Data) | R3 (Frontend) |
|---|---|---|---|
| **1-2** | Code search tool: GitHub API → index function/class signatures → semantic search | MCP server: wrap RAG, ClickHouse, and code search tools as MCP endpoints | Rich message components: code snippets with file links, log stream view |
| **3-4** | Skills framework: define `DiagnoseErrorSkill` (KeDB → Logs → Code → Summary) and `SearchDocsSkill` | Output guardrail: SQL read-only validator, response grounding check (does answer cite a source?) | Error display panel: trace visualization, log highlighting |
| **5** | Context linking workflow: User query → fetch logs → extract error sig → search code → return file path | Integration testing: MCP server with Claude Desktop or custom client | Polish chat UX, responsive layout, loading states |

**Phase 2 Deliverable:** User asks "Why is login failing?" → Agent checks logs, finds `NullPointerException` in `auth.py:42`, shows the code. MCP clients can call the same tools.

---

### Phase 3 — Reliability + Intelligence (Week 3)
**Goal:** Agent self-corrects, learns from past issues, and monitors proactively.

| Day | R1 (Agent) | R2 (Backend + Data) | R3 (Frontend) |
|---|---|---|---|
| **1-2** | Self-correction loop: catch SQL errors → parse error msg → rewrite SQL → retry (max 3) | KeDB implementation: vector store of (error_signature → root_cause → solution) tuples | HITL: Approval Card component (plan preview, approve/reject buttons) |
| **3-4** | HITL framework: `ApprovalGate` middleware — agent pauses, emits plan, waits for user decision | Proactive health check: APScheduler cron → `get_top_errors()` → analyze → generate report | "The Deck" dashboard: health feed, alert cards, system status |
| **5** | KeDB feedback loop: resolved issues auto-added to KeDB, agent checks KeDB first on new queries | Tool guardrails: rate limiter, timeout wrapper, scope limiter (allowed repos) | Connect Deck to health check API, real-time updates |

**Phase 3 Deliverable:** Agent auto-fixes bad SQL. Dashboard shows "PaymentService 5% error rate — click to investigate." Known errors resolve instantly from KeDB.

---

### Phase 4 — Reasoning + Browser Use + Polish (Week 4)
**Goal:** Agent handles complex queries, navigates web UIs, and system is demo-ready.

| Day | R1 (Agent) | R2 (Backend + Data) | R3 (Frontend) |
|---|---|---|---|
| **1-2** | Browser Use tool: integrate `browser-use` + Playwright — agent navigates Grafana, admin panels, creates dashboards via chat | `draft_github_issue` tool, `draft_pr` tool (create branch + commit) | Browser session viewer: live stream / screenshot display of agent's browser actions, HITL approval for UI actions |
| **3** | Multi-step reasoning: Chain of Thought + Correlation engine (cross-reference metrics, logs, traces) | End-to-end integration testing, load testing with concurrent users | Full responsive polish, dark mode, micro-animations |
| **4-5** | Concepts mapping document (learning artifact), final agent tuning | Security audit: prompt injection tests, PII leak tests, SQL injection tests, browser action safety tests | Demo recording, landing page with architecture diagram |

**Phase 4 Deliverable:** User asks "Create a Kubernetes dashboard in Grafana with pod CPU and memory panels" → Agent opens Grafana, creates the dashboard, adds panels, takes a screenshot, and shares the result. All UI actions require HITL approval before execution.

---

## 8. Key Use Cases (End-to-End Flows)

### Flow 1: Documentation Q&A
```
User: "How do I set up OAuth2 in your SDK?"
                    │
          ┌─────────▼──────────┐
          │  Perception: Parse  │
          │  intent = "how-to"  │
          └─────────┬──────────┘
          ┌─────────▼──────────┐
          │  Routing: Use RAG   │
          └─────────┬──────────┘
          ┌─────────▼──────────┐
          │  Action: search_docs│
          │  → FAISS retrieval  │
          └─────────┬──────────┘
          ┌─────────▼──────────┐
          │  Response: Answer   │
          │  with doc citations │
          └────────────────────┘
```

### Flow 2: Live Debugging
```
User: "My login API is returning 500 errors"
                    │
          ┌─────────▼───────────┐
          │  KeDB check: known? │──Yes──► Return cached solution
          └─────────┬───────────┘
                    No
          ┌─────────▼───────────┐
          │  query_clickhouse   │
          │  SELECT from logs   │
          │  WHERE service=auth │
          └─────────┬───────────┘
          ┌─────────▼───────────┐
          │  Self-correct SQL   │
          │  if query fails     │
          └─────────┬───────────┘
          ┌─────────▼───────────┐
          │  search_codebase    │
          │  find error source  │
          └─────────┬───────────┘
          ┌─────────▼───────────┐
          │  Synthesize answer  │
          │  + add to KeDB      │
          └─────────────────────┘
```

### Flow 3: Proactive Health Check
```
          ┌────────────────────┐
          │  Cron: every hour   │
          └─────────┬──────────┘
          ┌─────────▼──────────┐
          │  get_top_errors()   │
          │  from ClickHouse    │
          └─────────┬──────────┘
          ┌─────────▼──────────┐
          │  error_rate > 5%?   │──No──► Log "all green"
          └─────────┬──────────┘
                   Yes
          ┌─────────▼──────────┐
          │  DiagnoseErrorSkill │
          │  analyze + explain  │
          └─────────┬──────────┘
          ┌─────────▼──────────┐
          │  Post to Deck +     │
          │  notify team        │
          └────────────────────┘
```

### Flow 4: Browser Use (Web UI Automation)
```
User: "Create a Kubernetes dashboard in Grafana
        with pod CPU and memory charts"
                    │
          ┌─────────▼───────────┐
          │  Routing: intent =  │
          │  "UI action"        │
          └─────────┬───────────┘
          ┌─────────▼───────────┐
          │  Plan: Break into   │
          │  UI steps:          │
          │  1. Open Grafana    │
          │  2. New Dashboard   │
          │  3. Add CPU panel   │
          │  4. Add Memory panel│
          └─────────┬───────────┘
          ┌─────────▼───────────┐
          │  HITL: Show plan    │
          │  [Approve] [Reject] │
          └─────────┬───────────┘
                 Approved
          ┌─────────▼───────────┐
          │  Browser Use Tool:  │
          │  Playwright executes│
          │  each step, streams │
          │  screenshots        │
          └─────────┬───────────┘
          ┌─────────▼───────────┐
          │  Return: screenshot │
          │  + dashboard URL    │
          └─────────────────────┘
```

---

## 9. Folder Structure

```
devrel-agent/
├── apps/
│   ├── backend/                    # FastAPI
│   │   ├── main.py                 # App entry, CORS, routes
│   │   ├── agent/
│   │   │   ├── loop.py             # AgentLoop (4 cognitive layers)
│   │   │   ├── router.py           # Intent classifier / routing
│   │   │   └── planner.py          # Multi-step ReAct planner
│   │   ├── tools/
│   │   │   ├── registry.py         # Tool registration + selection
│   │   │   ├── rag_tool.py         # Docs/Swagger search (FAISS)
│   │   │   ├── clickhouse_tool.py  # NL → SQL → execute
│   │   │   ├── code_search_tool.py # GitHub codebase search
│   │   │   ├── kedb_tool.py        # Known Error DB lookup
│   │   │   ├── github_tool.py      # Issue/PR drafting
│   │   │   └── browser_tool.py     # Browser Use — Playwright web UI automation
│   │   ├── skills/
│   │   │   ├── diagnose_error.py   # KeDB → Logs → Code → Summary
│   │   │   ├── search_docs.py      # Multi-source doc search
│   │   │   └── create_patch.py     # Code fix → PR workflow
│   │   ├── guardrails/
│   │   │   ├── input_guard.py      # Topic filter, PII scrub, injection detect
│   │   │   ├── output_guard.py     # Grounding check, SQL safety
│   │   │   └── tool_guard.py       # Rate limit, timeout, scope
│   │   ├── memory/
│   │   │   ├── conversation.py     # Short-term chat history
│   │   │   └── kedb_store.py       # Long-term known error storage
│   │   ├── mcp/
│   │   │   └── server.py           # MCP server exposing tools
│   │   ├── scheduler/
│   │   │   └── health_check.py     # APScheduler cron jobs
│   │   └── models/
│   │       └── schemas.py          # Pydantic models
│   │
│   └── frontend/                   # Next.js
│       ├── components/
│       │   ├── ChatWidget.tsx       # Collapsible chat
│       │   ├── MessageBubble.tsx    # Rich messages (code, logs)
│       │   ├── SqlSandbox.tsx       # Show executed SQL
│       │   ├── ApprovalCard.tsx     # HITL plan review
│       │   └── DeckFeed.tsx         # Health dashboard feed
│       └── pages/
│           ├── index.tsx            # The Deck (dashboard)
│           └── api/                 # Next.js API routes (proxy)
│
├── data/
│   ├── docs/                       # Raw documentation to ingest
│   ├── faiss_index/                # Generated vector index
│   └── kedb/                       # Known error database
│
├── scripts/
│   ├── ingest_docs.py              # Doc → chunks → embeddings
│   └── seed_kedb.py                # Seed initial known errors
│
├── tests/
│   ├── test_tools/
│   ├── test_guardrails/
│   ├── test_skills/
│   └── test_e2e/
│
├── docker-compose.yml              # ClickHouse + app services
├── .env.example
└── README.md
```

---

## 10. Security & Guardrails Matrix

| Layer | Guardrail | Implementation | Priority |
|---|---|---|---|
| **Input** | Topic classifier | LLM-based: reject off-topic queries | P1 |
| **Input** | PII scrubber | Regex: strip emails, IPs, tokens from user input | P1 |
| **Input** | Prompt injection | Pattern matching + LLM judge | P2 |
| **Tool** | Read-only DB | ClickHouse user with `SELECT` only | P0 |
| **Tool** | Rate limiter | Max 10 tool calls per conversation | P1 |
| **Tool** | Scope limiter | `ALLOWED_REPOS` env var for GitHub access | P1 |
| **Tool** | Timeout | 30s max per tool execution | P1 |
| **Tool** | Browser sandbox | `ALLOWED_URLS` whitelist, no access to external sites | P0 |
| **Tool** | Browser HITL | Every browser action plan requires user approval before execution | P0 |
| **Output** | SQL safety | AST-parse SQL, reject `INSERT/UPDATE/DELETE/DROP` | P0 |
| **Output** | Grounding | Check response cites doc/log source | P2 |
| **Output** | HITL gate | Require approval for write actions | P0 |

---

## 11. Dependencies & Risks

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| LLM cost overrun | Budget | Medium | Use GPT-4o-mini for routing, GPT-4o only for complex reasoning |
| RAG quality (bad chunks) | Phase 1 accuracy | Medium | Invest 2 hrs in chunk size tuning + evaluation |
| GitHub API rate limits | Phase 2 blocks | Low | Cache indexed repos, use conditional requests |
| Frontend scope creep | Timeline | High | **Strict: Chat + Deck only. No CLI/IDE plugin.** |
| MCP spec changes | Phase 2 rework | Low | Pin SDK version, test with one client |
| ClickHouse downtime | All phases | Low | Team expertise + local Docker fallback |
| Browser Use reliability | Phase 4 flakiness | Medium | Limit to 2-3 target apps (e.g. Grafana), extensive HITL, fallback to manual instructions |

---

## 12. Demo Scenario (End-of-Project)

A 5-minute live demo showing:

1. **User asks:** "How do I configure rate limiting?" → Agent answers from docs with citations
2. **User asks:** "My payment API is slow" → Agent queries ClickHouse logs, finds `TimeoutException`, searches codebase, identifies `payment_handler.py:92`, suggests fix
3. **Dashboard shows:** "Alert: PaymentService error rate 8% ↑" — generated by proactive cron
4. **Agent proposes:** "I can create a GitHub issue with this analysis" → Approval Card appears → User approves → Issue created
5. **Same question again:** Agent answers instantly from KeDB → "Known issue, here's the fix from last time"
6. **User asks:** "Create a Kubernetes dashboard in Grafana with pod CPU and memory panels" → Agent shows the plan → User approves → Agent opens Grafana, creates the dashboard, takes a screenshot → Shares the result with the dashboard URL

---

## 13. Success Criteria

- [ ] Agent answers doc questions with >80% relevance (manual eval on 20 test queries)
- [ ] Agent queries ClickHouse and returns meaningful log analysis
- [ ] Agent maps errors to source code files
- [ ] KeDB reduces repeat investigation time
- [ ] All write actions go through HITL approval
- [ ] MCP server works with at least one external client
- [ ] Proactive health check runs on schedule
- [ ] Self-correction fixes at least 2/3 bad SQL queries
- [ ] Zero PII leakage in 50 test conversations
- [ ] Browser Use completes at least 3 UI tasks (e.g. create Grafana dashboard, configure alert, navigate admin panel)
- [ ] All browser actions go through HITL approval before execution
- [ ] End-to-end demo completes without failures

---

## 14. Concepts-to-Code Mapping (Learning Reference)

This is your personal reference to trace every agentic AI concept to its implementation:

```
Concept                → File / Module                    → What to Study
───────────────────────────────────────────────────────────────────────────
RAG                    → tools/rag_tool.py                → Chunking, embeddings, retrieval
Tool Selection         → tools/registry.py                → LLM function calling, tool schema
Cognitive Layers       → agent/loop.py                    → Perception → Routing → Memory → Action
MCP                    → mcp/server.py                    → Protocol spec, tool exposure
Skills                 → skills/diagnose_error.py         → Multi-tool composition
Input Guardrails       → guardrails/input_guard.py        → Topic filter, PII, injection
Output Guardrails      → guardrails/output_guard.py       → Grounding, SQL safety
Tool Guardrails        → guardrails/tool_guard.py         → Rate limit, timeout, scope
Self-Correction        → agent/loop.py (retry logic)      → Error parsing, SQL rewrite
HITL                   → guardrails/output_guard.py       → Approval gate pattern
Short-term Memory      → memory/conversation.py           → Chat history management
Long-term Memory       → memory/kedb_store.py             → Episodic memory, vector search
Proactive Agents       → scheduler/health_check.py        → Cron, anomaly detection
Multi-step Reasoning   → agent/planner.py                 → ReAct, Chain of Thought
Browser Use            → tools/browser_tool.py             → Playwright, browser-use, web UI automation
```
