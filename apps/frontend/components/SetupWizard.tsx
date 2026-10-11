"use client";

import React, { useState } from 'react';
import {
  Activity,
  ArrowLeft,
  ArrowRight,
  BookOpen,
  Check,
  CheckCircle2,
  CircleHelp,
  Database,
  FileCode2,
  Github,
  LoaderCircle,
  LockKeyhole,
  Radio,
  ShieldCheck,
  Sparkles,
  TriangleAlert,
  Workflow,
} from 'lucide-react';
import { useRouter } from 'next/navigation';
import { apiFetch } from '../lib/api';
import { withBasePath } from '../lib/app-config';
import { getIdentity, setIdentity, setProject } from '../lib/auth';
import { setSetupComplete } from '../lib/setup';

const FLOW = [
  { title: 'Understand', description: 'What DevRelAgent does' },
  { title: 'Workspace', description: 'Choose your local identity' },
  { title: 'Connect', description: 'Check your backend' },
];

function toSlug(value: string): string {
  return value.trim().toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '') || 'dev-workspace';
}

export function SetupWizard({ onComplete }: { onComplete: () => void }) {
  const router = useRouter();
  const identity = getIdentity();
  const [step, setStep] = useState(0);
  const [name, setName] = useState(identity.name);
  const [email, setEmail] = useState(identity.email);
  const [workspace, setWorkspace] = useState(identity.workspace.replace(/-/g, ' '));
  const [checking, setChecking] = useState(false);
  const [connection, setConnection] = useState<'idle' | 'ready' | 'offline'>('idle');
  const [connectionMessage, setConnectionMessage] = useState('');

  const isValidEmail = /^[^\s@]+@(?:localhost|(?:[^\s@]+\.)+[^\s@]+)$/i.test(email.trim());

  const saveProfile = () => {
    const current = getIdentity();
    const next = { name: name.trim(), email: email.trim(), workspace: toSlug(workspace) };
    setIdentity(next);
    if (current.workspace !== next.workspace) setProject(null);
  };

  const checkConnection = async () => {
    saveProfile();
    setChecking(true);
    setConnection('idle');
    setConnectionMessage('');
    try {
      const health = await apiFetch('/health');
      if (!health.ok) throw new Error(`Backend health check returned HTTP ${health.status}.`);
      const meResponse = await apiFetch('/auth/me');
      if (!meResponse.ok) throw new Error(`Backend is reachable, but workspace setup returned HTTP ${meResponse.status}.`);
      const me = await meResponse.json();
      const projectsResponse = await apiFetch('/projects');
      if (!projectsResponse.ok) throw new Error(`Backend is reachable, but projects could not be loaded (HTTP ${projectsResponse.status}).`);
      const projects = await projectsResponse.json();
      const active = projects.find((project: { id: string }) => project.id === me.project_id) ?? projects[0];
      setProject(active ? { id: active.id, name: active.name, slug: active.slug } : null);
      setConnection('ready');
      setConnectionMessage(`API connection verified for ${me.workspace_name || 'your workspace'}${me.project_name ? ` · ${me.project_name}` : ''}. Language-model and optional data-source readiness still depends on backend configuration.`);
    } catch (error) {
      setConnection('offline');
      setConnectionMessage(error instanceof Error ? error.message : 'Could not reach the backend.');
    } finally {
      setChecking(false);
    }
  };

  const finish = () => {
    saveProfile();
    setSetupComplete(true);
    onComplete();
    router.push('/');
  };

  return (
    <main className="setup-shell">
      <div className="setup-topbar">
        <a className="brand-lockup" href={withBasePath('/')} aria-label="DevRelAgent home">
          <span className="brand-mark"><Activity size={19} strokeWidth={2.5} /></span>
          <span>DevRel<span className="brand-muted">Agent</span></span>
        </a>
        <a className="setup-report-link" href={withBasePath('/guide')} target="_blank" rel="noreferrer">
          <BookOpen size={16} /> Project guide
        </a>
      </div>

      <div className="setup-layout">
        <section className="setup-main-card">
          <div className="setup-eyebrow"><Sparkles size={15} /> A better first run</div>
          <h1>Meet your new<br /><span>developer support copilot.</span></h1>
          <p className="setup-lead">
            DevRelAgent brings technical knowledge, code context and operational signals into one
            explainable workspace—so teams can investigate engineering questions with clearer evidence.
          </p>

          <div className="setup-progress" aria-label={`Setup step ${step + 1} of ${FLOW.length}`}>
            {FLOW.map((item, index) => (
              <div className={`setup-progress-step ${index <= step ? 'is-current' : ''}`} key={item.title}>
                <span className="setup-step-number">{index < step ? <Check size={14} /> : index + 1}</span>
                <span><strong>{item.title}</strong><small>{item.description}</small></span>
              </div>
            ))}
          </div>

          {step === 0 && (
            <div className="setup-step-content">
              <div className="setup-section-heading">
                <span className="setup-section-kicker">01 / WHAT IT DOES</span>
                <h2>One assistant. Your engineering context.</h2>
                <p>Ask a question in plain language. The agent classifies the intent, selects an available tool, runs guardrails, and returns an explanation with the result.</p>
              </div>
              <div className="capability-grid">
                <article className="capability-card"><span className="capability-icon icon-violet"><BookOpen size={18} /></span><h3>Find answers</h3><p>Search connected technical documentation and indexed code to understand setup, APIs and implementation details.</p></article>
                <article className="capability-card"><span className="capability-icon icon-blue"><Activity size={18} /></span><h3>Investigate issues</h3><p>When configured, query ClickHouse observability data and combine signals into a useful incident investigation.</p></article>
                <article className="capability-card"><span className="capability-icon icon-amber"><Workflow size={18} /></span><h3>Coordinate actions</h3><p>Review approval requests for supported higher-risk operations, with a visible plan and a recorded decision.</p></article>
              </div>
              <div className="setup-explainer">
                <div className="setup-explainer-icon"><FileCode2 size={20} /></div>
                <div><strong>How an answer is produced</strong><p>Question → intent routing → configured tools and project context → safety checks → response. Tool results depend on the integrations enabled by your administrator.</p></div>
              </div>
              <div className="setup-actions setup-actions-end">
                <button className="button-primary" onClick={() => setStep(1)}>Set up my workspace <ArrowRight size={17} /></button>
              </div>
            </div>
          )}

          {step === 1 && (
            <div className="setup-step-content">
              <div className="setup-section-heading">
                <span className="setup-section-kicker">02 / YOUR WORKSPACE</span>
                <h2>Make this space yours.</h2>
                <p>In local development, this profile identifies requests and provisions a workspace. It is stored in this browser—not an account or an authentication system.</p>
              </div>
              <div className="setup-form">
                <label>Your name<input value={name} onChange={(event) => setName(event.target.value)} placeholder="Alex Morgan" autoComplete="name" maxLength={100} /></label>
                <label>Email address<input type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="alex@company.com" autoComplete="email" required aria-invalid={email.length > 0 && !isValidEmail} />{email.length > 0 && !isValidEmail && <small className="setup-field-error">Enter a valid email address (or use dev@localhost for local setup).</small>}</label>
                <label>Workspace name<input value={workspace} onChange={(event) => setWorkspace(event.target.value)} placeholder="Platform Engineering" maxLength={80} /><small>Workspace slug: <code>{toSlug(workspace)}</code></small></label>
              </div>
              <div className="setup-note"><CircleHelp size={17} /><p><strong>Production authentication is separate.</strong> This frontend profile uses the backend's development identity headers. Before exposing the app to a network, configure a trusted OIDC provider (such as the backend's supported Clerk/OIDC mode) and integrate its sign-in flow.</p></div>
              <div className="setup-actions">
                <button className="button-quiet" onClick={() => setStep(0)}><ArrowLeft size={16} /> Back</button>
                <button className="button-primary" onClick={() => { saveProfile(); setStep(2); }} disabled={!name.trim() || !isValidEmail || !workspace.trim()}>Continue to connections <ArrowRight size={17} /></button>
              </div>
            </div>
          )}

          {step === 2 && (
            <div className="setup-step-content">
              <div className="setup-section-heading">
                <span className="setup-section-kicker">03 / CONNECTIONS</span>
                <h2>Check the essentials.</h2>
                <p>The browser can verify the backend and create your workspace. Provider keys and data-source credentials belong in the backend environment—not in this page.</p>
              </div>
              <div className="connection-list">
                <div className="connection-row"><span className="connection-icon"><Radio size={18} /></span><span><strong>DevRelAgent API</strong><small>Workspace, chat, approvals and project services</small></span><span className="connection-pill">Check now</span></div>
                <div className="connection-row"><span className="connection-icon"><Sparkles size={18} /></span><span><strong>Language model</strong><small>Set LLM_PROVIDER and its API key in apps/backend/.env</small></span><span className="connection-pill connection-optional">Server config</span></div>
                <div className="connection-row"><span className="connection-icon"><Database size={18} /></span><span><strong>Observability & knowledge</strong><small>Optional: ClickHouse, indexed code/docs, Grafana and GitHub</small></span><span className="connection-pill connection-optional">Optional</span></div>
              </div>
              {connection !== 'idle' && (
                <div className={`connection-result ${connection === 'ready' ? 'connection-result-good' : 'connection-result-bad'}`} role="status">
                  {connection === 'ready' ? <CheckCircle2 size={19} /> : <TriangleAlert size={19} />}
                  <div><strong>{connection === 'ready' ? 'API connection verified' : 'Backend setup needs attention'}</strong><p>{connectionMessage}</p></div>
                </div>
              )}
              <div className="setup-note setup-security-note"><LockKeyhole size={17} /><p>Approval and audit features improve oversight; they do not guarantee safe or correct outcomes. Review important findings and keep secrets out of prompts.</p></div>
              <div className="setup-actions">
                <button className="button-quiet" onClick={() => setStep(1)}><ArrowLeft size={16} /> Back</button>
                <div className="setup-action-group">
                  <button className="button-secondary" onClick={() => void checkConnection()} disabled={checking}>
                    {checking ? <LoaderCircle className="spin-icon" size={16} /> : <Radio size={16} />}
                    {checking ? 'Checking…' : 'Verify connection'}
                  </button>
                  <button className="button-primary" onClick={finish}>
                    {connection === 'ready' ? 'Open DevRelAgent' : 'Continue to the app'} <ArrowRight size={17} />
                  </button>
                </div>
              </div>
              <p className="setup-small-print">If the backend is offline, you can still explore the interface. Chat and workspace operations need a running, configured backend.</p>
            </div>
          )}
        </section>

        <aside className="setup-sidebar">
          <div className="setup-sidebar-card setup-visual-card">
            <div className="visual-topline"><span className="live-dot" /> ENGINEERING CONTEXT</div>
            <div className="visual-orbit orbit-one" /><div className="visual-orbit orbit-two" />
            <div className="visual-core"><Activity size={27} /></div>
            <div className="visual-node node-docs"><BookOpen size={15} /><span>Docs</span></div>
            <div className="visual-node node-code"><FileCode2 size={15} /><span>Code</span></div>
            <div className="visual-node node-data"><Database size={15} /><span>Signals</span></div>
            <div className="visual-node node-github"><Github size={15} /><span>Tools</span></div>
            <p className="visual-caption">A connected view of the sources you choose to configure.</p>
          </div>
          <div className="setup-sidebar-card principles-card">
            <span className="setup-section-kicker">BUILT FOR HUMAN OVERSIGHT</span>
            <div className="principle-row"><ShieldCheck size={19} /><span><strong>Scoped workspaces</strong><small>Workspace and project context is attached to backend requests.</small></span></div>
            <div className="principle-row"><Workflow size={19} /><span><strong>Review before risky actions</strong><small>Supported approval-gated operations surface in the review inbox.</small></span></div>
            <div className="principle-row"><Activity size={19} /><span><strong>Traceable operations</strong><small>Audit history, request IDs and metrics support investigation.</small></span></div>
          </div>
          <div className="setup-sidebar-card truth-card">
            <TriangleAlert size={17} /><p><strong>Know the boundaries.</strong> This is an actively developed, self-hosted prototype—not a certified support or incident-response system. Capabilities vary with configured tools and indexed data.</p>
          </div>
          <a className="setup-full-guide" href={withBasePath('/guide')} target="_blank" rel="noreferrer">Explore the full product guide <ArrowRight size={15} /></a>
        </aside>
      </div>
      <footer className="setup-footer"><span>DEVRELAGENT · SELF-HOSTED DEVELOPER SUPPORT</span><span>Built to make engineering context easier to explore.</span></footer>
    </main>
  );
}
