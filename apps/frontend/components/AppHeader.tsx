"use client";

import React from 'react';
import { Activity, Bot, Building2, ShieldCheck, Sparkles } from 'lucide-react';
import { useRouter } from 'next/navigation';
import { ProjectSwitcher } from './ProjectSwitcher';

export type TabKey = 'chat' | 'dashboard' | 'approvals' | 'workspace';

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

  return (
    <header className="app-shell-header">
      <div className="app-header-main">
        <button className="app-brand" onClick={() => router.push('/')} aria-label="Open DevRelAgent chat">
          <span className="app-brand-mark"><Activity size={18} strokeWidth={2.5} /></span>
          <span className="app-brand-name">DevRel<span>Agent</span></span>
        </button>
        <div className="app-page-heading">
          <h1>{title}</h1>
          {subtitle && <p>{subtitle}</p>}
        </div>
        <div className="app-header-workspace"><ProjectSwitcher /></div>
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
        <a className="app-nav-guide" href="/project-report" target="_blank" rel="noreferrer">
          <Sparkles size={15} /><span>Guide</span>
        </a>
      </nav>
    </header>
  );
}

export default AppHeader;
