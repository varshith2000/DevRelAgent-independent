import type { Metadata } from 'next';
import Link from 'next/link';
import {
  Activity,
  ArrowDown,
  ArrowRight,
  ArrowUpRight,
  BookOpen,
  Boxes,
  CheckCircle2,
  CircleHelp,
  Code2,
  Compass,
  Database,
  FileSearch,
  Github,
  GitPullRequest,
  LockKeyhole,
  Network,
  Radar,
  ShieldCheck,
  Sparkles,
  Workflow,
} from 'lucide-react';
import { AppHeader } from '../../components/AppHeader';
import { withBasePath } from '../../lib/app-config';

export const metadata: Metadata = {
  title: 'Product guide — DevRelAgent',
  description: 'What DevRelAgent does, what makes it different, how to connect engineering context, and what it takes to deploy responsibly.',
};

const principles = [
  {
    icon: Network,
    number: '01',
    title: 'One question, more context',
    text: 'Bring code search, technical knowledge and operational signals into the same investigation—when those sources are indexed and configured.',
    tone: 'mint',
  },
  {
    icon: ShieldCheck,
    number: '02',
    title: 'Explain before consequential action',
    text: 'Supported write-like tools can be routed through a human review queue. People stay accountable for the decision.',
    tone: 'amber',
  },
  {
    icon: LockKeyhole,
    number: '03',
    title: 'Designed for your environment',
    text: 'A self-hostable architecture and workspace/project boundaries let an organization control its deployment and integrations.',
    tone: 'blue',
  },
];

const workflow = [
  ['01', 'Ask', 'Describe the issue, goal, service or code question.'],
  ['02', 'Route', 'Input checks and intent routing select an available tool or skill.'],
  ['03', 'Gather', 'Configured indexes and integrations return evidence for this project.'],
  ['04', 'Review', 'Guardrails validate the response; supported risky actions request approval.'],
  ['05', 'Learn', 'Use the answer, inspect activity and keep a record of approval decisions.'],
];

const capabilities = [
  { icon: FileSearch, title: 'Documentation & code discovery', availability: 'Requires indexed sources', copy: 'Search technical docs and a repository index; inspect relevant files and implementation context.' },
  { icon: Radar, title: 'Incident investigation', availability: 'Requires live data integrations', copy: 'Ask about errors and service health using configured observability tools, such as ClickHouse or Grafana.' },
  { icon: GitPullRequest, title: 'Team handoffs', availability: 'Tools and credentials required', copy: 'Prepare supported GitHub issue or pull-request workflows, with approval controls where configured.' },
  { icon: Activity, title: 'Operational visibility', availability: 'Backend services required', copy: 'Review incoming alert activity, service-status signals, approval history and workspace operations.' },
];

const launchSteps = [
  'Run the FastAPI backend and Next.js frontend; verify the API health and workspace endpoints.',
  'Configure trusted authentication before exposing the service beyond a local development environment.',
  'Set provider credentials on the server, then connect and validate only the data sources you intend to use.',
  'Clone/index a permitted repository using the code-search tooling; test retrieval against known files and questions.',
  'Exercise approval, audit, tenant isolation, backups, rate limits and failure paths in a non-production environment.',
];

export default function GuidePage() {
  return (
    <div className="app-page-frame guide-page-frame">
      <AppHeader active="guide" title="Product guide" subtitle="The product, the workflow, and the honest boundaries" />
      <main className="guide-main">
        <section className="guide-hero" aria-labelledby="guide-title">
          <div className="guide-hero-copy">
            <div className="guide-eyebrow"><span className="guide-eyebrow-dot" /> PRODUCT BRIEF <span>/</span> ENGINEERING INTELLIGENCE</div>
            <h1 id="guide-title">Engineering answers,<br /><em>with the full picture.</em></h1>
            <p className="guide-lead">DevRelAgent is a self-hostable engineering-support agent that can connect a developer question to configured documentation, repository code and operational evidence—with a human in the loop for supported consequential actions.</p>
            <div className="guide-hero-actions">
              <Link className="guide-primary-cta" href="/?setup=1">Explore the workspace <ArrowRight size={16} /></Link>
              <a className="guide-secondary-cta" href="#why-devrel">See what makes it different <ArrowDown size={15} /></a>
            </div>
            <p className="guide-honesty"><CircleHelp size={14} /> Capability depends on configured providers, integrations, indexed data and deployment.</p>
          </div>
          <div className="guide-hero-visual" aria-label="Illustration of a question drawing evidence from code, documentation and live signals, with human review">
            <div className="guide-visual-top"><span><Sparkles size={14} /> CONTEXT GRAPH</span><span>FLOW / 01</span></div>
            <div className="guide-graph">
              <div className="guide-graph-ring guide-graph-ring-a" /><div className="guide-graph-ring guide-graph-ring-b" />
              <div className="guide-graph-core"><Activity size={23} /><span>AGENT</span></div>
              <div className="guide-graph-node guide-node-code"><Code2 size={14} /> CODE</div>
              <div className="guide-graph-node guide-node-docs"><BookOpen size={14} /> DOCS</div>
              <div className="guide-graph-node guide-node-signals"><Database size={14} /> SIGNALS</div>
              <div className="guide-graph-node guide-node-human"><ShieldCheck size={14} /> HUMAN REVIEW</div>
              <i className="guide-graph-pulse guide-pulse-one" /><i className="guide-graph-pulse guide-pulse-two" />
            </div>
            <div className="guide-visual-foot"><span>YOUR SOURCES</span><span>YOUR POLICIES</span><span>YOUR DECISION</span></div>
          </div>
        </section>

        <section className="guide-thesis" id="why-devrel">
          <div className="guide-section-heading"><span>THE DIFFERENCE</span><h2>Not another answer box.<br /><em>An engineering-context layer.</em></h2></div>
          <p>Most support starts with a question and ends with a link. The DevRelAgent product thesis is to join the dots across the sources a team already trusts—while making tool use inspectable and high-impact actions reviewable.</p>
        </section>
        <section className="guide-principle-grid" aria-label="DevRelAgent differentiators">
          {principles.map(({ icon: Icon, number, title, text, tone }) => (
            <article className={`guide-principle-card guide-tone-${tone}`} key={number}>
              <div className="guide-card-top"><span className="guide-icon-box"><Icon size={18} /></span><span>{number} / 03</span></div>
              <h3>{title}</h3><p>{text}</p><div className="guide-card-rule" />
            </article>
          ))}
        </section>

        <section className="guide-workflow-section">
          <div className="guide-section-heading"><span>HOW THE AGENT WORKS</span><h2>From question to <em>grounded next step.</em></h2></div>
          <div className="guide-workflow">
            {workflow.map(([number, title, text], index) => (
              <article className="guide-workflow-step" key={number}>
                <div className="guide-workflow-index"><span>{number}</span>{index < workflow.length - 1 && <i />}</div>
                <div><h3>{title}</h3><p>{text}</p></div>
              </article>
            ))}
          </div>
        </section>

        <section className="guide-capabilities-section" id="capabilities">
          <div className="guide-section-heading guide-capabilities-heading"><div><span>WHAT IT CAN DO</span><h2>Useful today. <em>Expandable by design.</em></h2></div><span className="guide-availability-note"><span /> CONFIGURATION REQUIRED</span></div>
          <div className="guide-capability-grid">
            {capabilities.map(({ icon: Icon, title, availability, copy }, index) => (
              <article className="guide-capability-card" key={title}>
                <div className="guide-capability-icon"><Icon size={19} /></div><span className="guide-capability-number">0{index + 1}</span>
                <h3>{title}</h3><p>{copy}</p><span className="guide-capability-status"><i /> {availability}</span>
              </article>
            ))}
          </div>
        </section>

        <section className="guide-codebase-section">
          <div className="guide-codebase-copy">
            <span className="guide-section-kicker">WHEN IT KNOWS THE CODEBASE</span>
            <h2>Go beyond “try restarting.”</h2>
            <p>Once an authorized repository has been cloned and indexed and the relevant tools are active, the agent can search code semantically and inspect files. Add documentation and runtime signals to investigate a wider slice of the problem—not just the symptom.</p>
            <ul className="guide-check-list">
              <li><CheckCircle2 size={16} /> Find likely implementations and related files faster.</li>
              <li><CheckCircle2 size={16} /> Explain code paths alongside indexed documentation.</li>
              <li><CheckCircle2 size={16} /> Correlate a reported symptom with configured operational evidence.</li>
              <li><CheckCircle2 size={16} /> Turn a verified gap into a reviewable team handoff where integrations allow.</li>
            </ul>
            <p className="guide-caveat">Important: code search requires a repository index. The current web workspace does not provide a complete secure repository-connect wizard; administrators must provision indexing through the backend tooling. Verify results in source before acting.</p>
          </div>
          <div className="guide-source-stack">
            <div className="guide-source-card"><span className="guide-source-icon source-code"><Github size={17} /></span><span><strong>Repository</strong><small>Clone · parse · index · search</small></span><span className="guide-source-state">WHEN INDEXED</span></div>
            <div className="guide-source-join"><span /><span /><span /></div>
            <div className="guide-source-card"><span className="guide-source-icon source-docs"><BookOpen size={17} /></span><span><strong>Docs & API reference</strong><small>Ingest · retrieve · explain</small></span><span className="guide-source-state">WHEN CONNECTED</span></div>
            <div className="guide-source-join"><span /><span /><span /></div>
            <div className="guide-source-card"><span className="guide-source-icon source-signal"><Radar size={17} /></span><span><strong>Logs & service signals</strong><small>Query · compare · investigate</small></span><span className="guide-source-state">WHEN CONFIGURED</span></div>
            <div className="guide-source-result"><Workflow size={16} /><span><strong>One investigation</strong><small>Evidence stays attributable to its source</small></span><ArrowUpRight size={15} /></div>
          </div>
        </section>

        <section className="guide-journey-section">
          <div className="guide-section-heading"><span>WHERE IT CAN GO</span><h2>A practical path from <em>copilot to platform.</em></h2></div>
          <div className="guide-journey-grid">
            <article><span>NOW / CONFIGURED</span><h3>Engineering support</h3><p>Answer product and implementation questions with repository, documentation and service context.</p></article>
            <article><span>NEXT / VALIDATE</span><h3>Repeatable investigations</h3><p>Package trusted multi-step runbooks, citations, feedback and known-issue workflows around real team needs.</p></article>
            <article><span>LATER / BUILD & GOVERN</span><h3>Team agent platform</h3><p>Expand to integrations, policy controls, analytics and customer-facing support experiences after security, reliability and demand are proven.</p></article>
          </div>
          <p className="guide-roadmap-note">The latter two are product opportunities, not a promise that every workflow is implemented in this prototype.</p>
        </section>

        <section className="guide-commercial-section" id="commercial-model">
          <div className="guide-commercial-intro"><span className="guide-section-kicker">COMMERCIAL THESIS · TO VALIDATE</span><h2>Sell the trusted<br /><em>outcome—not tokens.</em></h2><p>Start with an engineering-support pilot where repeated questions, slow handoffs or noisy investigations have an observable cost. Price only after deployment effort, model spend, support load and buyer value are measured.</p></div>
          <div className="guide-commercial-options">
            <article><span>01</span><div><h3>Paid proof of value</h3><p>Fixed-scope setup, one team, a few sources and agreed success measures.</p></div><span className="guide-commercial-tag">BEST FIRST OFFER</span></article>
            <article><span>02</span><div><h3>Annual self-hosted license</h3><p>Charge for ongoing product updates, admin features and support; customer operates its own infrastructure.</p></div><Boxes size={17} /></article>
            <article><span>03</span><div><h3>Enterprise package</h3><p>Offer additional identity, governance, deployment and integration work only when implemented and supportable.</p></div><LockKeyhole size={17} /></article>
          </div>
          <p className="guide-commercial-footnote"><CircleHelp size={14} /> Packaging ideas only—no validated price, market-size, savings or security-certification claim is implied.</p>
        </section>

        <section className="guide-launch-section" id="getting-started">
          <div className="guide-section-heading"><span>THE OPERATOR'S CHECKLIST</span><h2>Connect it <em>without guesswork.</em></h2></div>
          <ol>{launchSteps.map((step, index) => <li key={step}><span>0{index + 1}</span><p>{step}</p></li>)}</ol>
          <div className="guide-launch-links"><Link href="/?setup=1">Open the onboarding walkthrough <ArrowRight size={15} /></Link><a href={withBasePath('/project-report')} target="_blank" rel="noreferrer">Read the full implementation and deployment report <ArrowUpRight size={15} /></a></div>
        </section>

        <section className="guide-trust-banner"><span className="guide-trust-icon"><ShieldCheck size={21} /></span><div><strong>Trust is a product feature. It is not a certification.</strong><p>The repository is an actively developed prototype. Default development identity is not production authentication; approvals and guardrails do not guarantee safe or correct outcomes. Before a customer deployment, complete security review, trusted OIDC integration, tenant-isolation tests, operational runbooks, and an honest capability demonstration.</p></div><Compass size={20} /></section>
        <footer className="guide-footer"><span>DEVRELAGENT <i>·</i> PRODUCT GUIDE</span><Link href="/">RETURN TO COMMAND CENTER <ArrowUpRight size={13} /></Link></footer>
      </main>
    </div>
  );
}
