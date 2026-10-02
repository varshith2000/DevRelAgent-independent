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

> **Project status: active development / prototype.** There is currently **no
> authentication** on the API and **no multi-tenant isolation**. These are the
> first deliverables of the roadmap (Phase 1). Do not expose this service to an
> untrusted network.

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

### Deployment Considerations

- **Single-tenant today**: multi-tenant isolation is on the roadmap, not implemented
- **Not certified**: DevRelAgent holds no security certification and makes no
  compliance guarantee. It implements some controls that *support* compliance
  work (PII redaction, audit logging, approval gates); certification would
  require an independent audit.
- **Scale**: the API is async and can run multiple replicas, but sessions and
  vector indexes are currently process-local
- **Monitoring**: health and metrics endpoints are provided

### Support

For production deployments:
- **Documentation**: [Project Wiki](https://github.com/your-org/DevRelAgent/wiki)
- **Issues**: [GitHub Issues](https://github.com/your-org/DevRelAgent/issues)
- **Security**: security@example.com
- **Support**: support@example.com
