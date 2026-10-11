"use client";

import React from 'react';
import { Activity, BookOpen, Bot, Building2, ShieldCheck, Sparkles, GitBranch } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { ProjectSwitcher } from './ProjectSwitcher';
import { DEMO_MODE, withBasePath } from '../lib/app-config';

export type TabKey = 'chat' | 'dashboard' | 'approvals' | 'workspace' | 'guide';

interface Tab {
  key: TabKey;
  label: string;
  href: string;
  icon: typeof Bot;
}

const TABS: Tab[] = [
  { key: 'chat', label: 'Chat', href: '/', icon: Bot },
  { key: 'dashboard', label: 'Dashboard', href: '/dashboard', icon: Activity },
  { key: 'approvals', label: 'Approvals', href: '/approvals', icon: ShieldCheck },
  { key: 'workspace', label: 'Workspace', href: '/workspace', icon: Building2 },
  { key: 'guide', label: 'Guide', href: '/guide', icon: Sparkles },
];

interface AppHeaderProps {
  active: TabKey;
  title?: string;
  subtitle?: string;
}

/**
 * Shared top bar: brand, project switcher and the primary navigation tabs.
 * Kept in one place so every page offers the same navigation.
 */
export function AppHeader({ active, title = 'DevRel Agent', subtitle }: AppHeaderProps) {
  const router = useRouter();
  // The static export emits the report as a plain file; a served app exposes the route.
  const reportHref = withBasePath(DEMO_MODE ? '/project-report.md' : '/project-report');

  return (
    <header className="app-shell-header">
      <div className="app-header-main">
        <button className="app-brand" onClick={() => router.push('/')} aria-label="Open DevRelAgent chat">
          <span className="app-brand-mark"><Activity size={18} strokeWidth={2.5} /></span>
          <span className="app-brand-lockup"><span className="app-brand-name">DEVREL<span>AGENT</span></span><span className="app-brand-edition">ENGINEERING INTELLIGENCE</span></span>
        </button>
        <div className="app-page-heading">
          <h1>{title}</h1>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <div className="app-header-workspace"><ProjectSwitcher /></div>
        <div className="app-header-meta"><span><GitBranch size={12} /> WORKSPACE / SCOPED</span><span className="app-header-meta-divider" /><span><ShieldCheck size={12} /> ACTIONS / REVIEW-GATED</span></div>
      </div>
      <nav className="app-primary-nav" aria-label="Main navigation">
        {TABS.map((tab) => {
          const Icon = tab.icon;
          const isActive = tab.key === active;
          return (
            <button
              key={tab.key}
              onClick={() => router.push(tab.href)}
              aria-current={isActive ? 'page' : undefined}
              className={`app-nav-item ${isActive ? 'app-nav-item-active' : ''}`}
            >
              <Icon size={16} />
              <span>{tab.label}</span>
            </button>
          );
        })}
        <a className="app-nav-guide app-nav-report" href={reportHref} target="_blank" rel="noreferrer">
          <BookOpen size={15} /><span>Project report</span>
        </a>
        {DEMO_MODE && (
          <span
            className="app-nav-demo"
            title="Static demo build: every log line, metric and approval is synthetic sample data."
          >
            <Sparkles size={12} /><span>Demo data</span>
          </span>
        )}
      </nav>
    </header>
  );
}

export default AppHeader;
