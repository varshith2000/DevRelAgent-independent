# Static demo site (GitHub Pages)

The full product needs a FastAPI backend, a database and telemetry storage. To let
people look at the interface without any of that, the frontend can be compiled as
a **backend-less demo build**: identical UI, identical interaction, but every
request is answered from a checked-in synthetic dataset.

- **URL (once Pages is enabled):** https://varshith2000.github.io/DevRelAgent-independent/
- **Workflow:** [`.github/workflows/pages.yml`](../.github/workflows/pages.yml)
- **Fixtures:** [`apps/frontend/lib/demo-data.ts`](../apps/frontend/lib/demo-data.ts)

> The account's user site (`varshith2000.github.io`) has the custom domain
> `varshithchennuru.dev`, which makes every `varshith2000.github.io/<repo>/` URL a
> 301 to `varshithchennuru.dev/<repo>/` — that redirect applies to project pages
> too. So the demo is served at
> **https://varshithchennuru.dev/DevRelAgent-independent/**, and the base path the
> workflow builds with (`/DevRelAgent-independent`) is correct for both hosts.

## What the demo contains

Everything is synthetic and modelled on the `orders-api` connection-pool incident
that already ships with the repository ([`scripts/fixtures/demo_incident.jsonl`](../scripts/fixtures/demo_incident.jsonl)):

| Surface | Demo behaviour |
| --- | --- |
| Chat | Keyword-routed answers citing log lines, trace ids, latency metrics and tool calls; unknown questions explain the demo |
| Dashboard | 8 services with health states, 6 alerts with relative timestamps, and a simulated live stream that pushes a new alert every ~20s |
| Approvals | 3 pending approvals (critical/high/low) plus 5 recorded decisions; approving or rejecting updates the queue and history in memory |
| Workspace | Workspace + 4 members, 3 projects (one archived), project API keys; creating/archiving projects and creating/revoking keys all work against in-memory state |
| Project report | The repository's `PROJECT_REPORT.md`, exported as a static file |

Data resets on every page load. No credentials, no backend and no external
requests are involved — the only network traffic is the site's own assets.

## How demo mode works

Two build-time flags (see [`apps/frontend/lib/app-config.ts`](../apps/frontend/lib/app-config.ts)):

| Variable | Effect |
| --- | --- |
| `NEXT_PUBLIC_DEMO_MODE=true` | Routes `apiFetch` to the fixture adapter, simulates the dashboard event stream, turns on the "Demo data" chip, and switches `next.config.ts` to `output: 'export'` |
| `NEXT_PUBLIC_BASE_PATH=/<repo>` | Builds with that `basePath`, as required by GitHub project pages |

Supporting code:

- `lib/demo.ts` — `demoFetch` (read endpoints, mutations, simulated latency) and `demoStream` (dashboard SSE stand-in). Imported dynamically, so a normal build never ships it.
- `lib/stream.ts` — one `openStream` call for both builds: a real `EventSource`, or the simulated emitter.
- `lib/api.ts` — `apiFetch` delegates to the demo adapter when the flag is on.

## Build and preview locally

```bash
cd apps/frontend
npm ci
NEXT_PUBLIC_DEMO_MODE=true NEXT_PUBLIC_BASE_PATH=/DevRelAgent-independent npm run build
# The export is written to apps/frontend/out/
cp out/project-report out/project-report.md   # same step the workflow runs
```

Serve the export the way Pages does — from a directory named after the repo:

```bash
mkdir -p /tmp/pages && ln -s "$PWD/out" /tmp/pages/DevRelAgent-independent
cd /tmp/pages && python3 -m http.server 8080
# → http://localhost:8080/DevRelAgent-independent/
```

For interactive development of the demo data, run the normal dev server with the
flag set: `NEXT_PUBLIC_DEMO_MODE=true npm run dev`.

Without `NEXT_PUBLIC_DEMO_MODE`, both `npm run build` and `npm run dev` behave
exactly as before: a server-rendered app that talks to `NEXT_PUBLIC_API_URL`.

## Deploying

Pushing to `varshith/devRel` (or `main`) with changes under `apps/frontend/`
triggers the workflow, which builds the export, copies the project report to a
`.md` asset, uploads it as a Pages artifact and deploys it. `workflow_dispatch`
runs it manually.

### One-time repository setup

GitHub Pages must be enabled once before the first deployment can succeed.
Either:

1. **Repository settings (simplest):** *Settings → Pages → Build and deployment →
   Source: GitHub Actions.* No token needed; the workflow then deploys on every
   qualifying push.
2. **From the workflow:** create a secret named `PAGES_SETUP_TOKEN` — a PAT with
   the `repo` scope (or a fine-grained token with Pages `write` + Administration
   `write`) — and the "Enable Pages (first run only)" step calls the Pages API
   with `enablement: true`. `GITHUB_TOKEN` cannot enable Pages, which is why this
   is opt-in and skipped when the secret is absent.

> **Private repository?** GitHub Pages for private repositories needs a paid plan
> (Pro/Team/Enterprise); the Free plan only publishes Pages for public
> repositories. If the plan does not allow it, make the repository public or
> check the plan before the first run. On Enterprise Cloud the published site can
> also be restricted to organisation members.

### Troubleshooting

`Error: Get Pages site failed ... Error: Not Found` from `actions/configure-pages`
means the repository has no Pages site yet — the build job above it succeeded and
the demo export is fine. Confirm that *Settings → Pages → Source* is **GitHub
Actions** (not "Deploy from a branch"), or supply `PAGES_SETUP_TOKEN` and re-run so
the enablement step creates the site. The error shows up in the `deploy` job, not
in `build`, which is how to tell it apart from a failing static export.

## Verification performed

The static export was built and served from a sub-path directory, then exercised
in headless Chrome against `http://127.0.0.1:8080/DevRelAgent-independent/`:
27 checks covering chat answers, tool-call and SQL rendering, dashboard alerts and
the simulated live indicator, the approval queue and a full approve flow, the
workspace/members/projects/API-key views, the project-report asset, a dashboard
deep link into a prefilled chat, base-path-correct navigation, and a clean
console. The fixture adapter was additionally asserted directly in Node
(read endpoints, mutations, error paths, chat intent routing).
