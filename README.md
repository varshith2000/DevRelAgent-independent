# DevRelAgent

> 24/7 AI-Powered Developer Relations Agent — Combines RAG, observability, code intelligence, browser automation, and a Known Error Database to supercharge developer support.

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
