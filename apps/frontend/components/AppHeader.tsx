"use client";

import React from 'react';
import { Activity, Bot, Building2, ShieldCheck } from 'lucide-react';
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
    <header className="bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 px-6 py-4">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <Activity className="w-7 h-7 text-blue-600 dark:text-blue-400" />
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{title}</h1>
            {subtitle && (
              <p className="text-sm text-gray-500 dark:text-gray-400">{subtitle}</p>
            )}
          </div>
        </div>

        <div className="flex items-center space-x-3">
          <ProjectSwitcher />

          <div className="flex items-center space-x-2 bg-gray-100 dark:bg-gray-900 rounded-lg p-1">
            {TABS.map((tab) => {
              const Icon = tab.icon;
              const isActive = tab.key === active;
              return (
                <button
                  key={tab.key}
                  onClick={() => router.push(tab.href)}
                  className={`flex items-center space-x-2 px-4 py-2 rounded-md text-sm font-medium transition-colors ${
                    isActive
                      ? 'bg-white dark:bg-gray-800 text-gray-900 dark:text-white shadow-sm'
                      : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-200 dark:hover:bg-gray-800'
                  }`}
                >
                  <Icon className="w-4 h-4" />
                  <span>{tab.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>
    </header>
  );
}

export default AppHeader;
