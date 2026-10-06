"use client";

import React, { useCallback, useEffect, useState } from 'react';
import {
  Building2,
  Check,
  FolderPlus,
  KeyRound,
  RefreshCw,
  Trash2,
  Users,
} from 'lucide-react';
import { apiFetch } from '../lib/api';
import { getProject, setProject, type ProjectRef } from '../lib/auth';
import type {
  ApiKey,
  ApiKeyCreated,
  Member,
  Project,
  Workspace,
} from '../lib/types';

function toProjectRef(project: Project): ProjectRef {
  return { id: project.id, name: project.name, slug: project.slug };
}

function formatDate(value: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString();
}

/**
 * Tenant administration: workspace + members, project lifecycle, and project
 * API keys. Mutating actions are only offered to owners/admins.
 */
export function WorkspaceAdmin({ className = '' }: { className?: string }) {
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [projects, setProjects] = useState<Project[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [keys, setKeys] = useState<ApiKey[]>([]);

  const [newProjectName, setNewProjectName] = useState('');
  const [newKeyName, setNewKeyName] = useState('');
  const [freshKey, setFreshKey] = useState<string | null>(null);

  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const canAdmin = workspace?.role === 'owner' || workspace?.role === 'admin';
  const canCreateProject = workspace?.role === 'owner';

  const loadBase = useCallback(async () => {
    try {
      const [workspaceResponse, membersResponse, projectsResponse] = await Promise.all([
        apiFetch('/workspaces/current'),
        apiFetch('/workspaces/current/members'),
        apiFetch('/projects'),
      ]);
      if (!workspaceResponse.ok) throw new Error(`workspace request failed (${workspaceResponse.status})`);
      if (!projectsResponse.ok) throw new Error(`projects request failed (${projectsResponse.status})`);

      const ws = (await workspaceResponse.json()) as Workspace;
      const memberList = membersResponse.ok ? ((await membersResponse.json()) as Member[]) : [];
      const projectList = (await projectsResponse.json()) as Project[];

      setWorkspace(ws);
      setMembers(memberList);
      setProjects(projectList);

      const stored = getProject();
      const current =
        projectList.find((project) => project.id === stored?.id) ?? projectList[0] ?? null;
      setActiveId(current?.id ?? null);
      setProject(current ? toProjectRef(current) : null);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load workspace');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadKeys = useCallback(async (projectId: string) => {
    try {
      const response = await apiFetch(`/projects/${projectId}/api-keys`);
      if (!response.ok) throw new Error(`api keys request failed (${response.status})`);
      setKeys((await response.json()) as ApiKey[]);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load API keys');
    }
  }, []);

  useEffect(() => {
    void loadBase();
  }, [loadBase]);

  useEffect(() => {
    if (activeId && canAdmin) void loadKeys(activeId);
    else setKeys([]);
  }, [activeId, canAdmin, loadKeys]);

  const selectProject = (project: Project) => {
    setActiveId(project.id);
    setProject(toProjectRef(project));
    setFreshKey(null);
  };

  const createProject = async () => {
    if (!newProjectName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch('/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newProjectName.trim() }),
      });
      if (!response.ok) throw new Error(`create failed (${response.status})`);
      const created = (await response.json()) as Project;
      setNewProjectName('');
      await loadBase();
      selectProject(created);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create project');
    } finally {
      setBusy(false);
    }
  };

  const archiveProject = async (project: Project) => {
    if (!window.confirm(`Archive “${project.name}”? It will disappear from active project selectors.`)) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch(`/projects/${project.id}/archive`, { method: 'POST' });
      if (!response.ok) throw new Error(`archive failed (${response.status})`);
      await loadBase();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to archive project');
    } finally {
      setBusy(false);
    }
  };

  const createKey = async () => {
    if (!activeId || !newKeyName.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch(`/projects/${activeId}/api-keys`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newKeyName.trim(), scopes: [] }),
      });
      if (!response.ok) throw new Error(`create key failed (${response.status})`);
      const created = (await response.json()) as ApiKeyCreated;
      setNewKeyName('');
      setFreshKey(created.key);
      await loadKeys(activeId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create API key');
    } finally {
      setBusy(false);
    }
  };

  const revokeKey = async (keyId: string) => {
    if (!activeId) return;
    setBusy(true);
    setError(null);
    try {
      const response = await apiFetch(`/projects/${activeId}/api-keys/${keyId}`, {
        method: 'DELETE',
      });
      if (!response.ok) throw new Error(`revoke failed (${response.status})`);
      await loadKeys(activeId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to revoke API key');
    } finally {
      setBusy(false);
    }
  };

  const activeProject = projects.find((project) => project.id === activeId) ?? null;

  return (
    <div className={`workspace-admin-shell ${className}`}>
      <div className="workspace-admin-content px-6 py-6 space-y-6 max-w-5xl">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold text-gray-900 dark:text-white">Workspace</h2>
          <button
            onClick={() => void loadBase()}
            className="flex items-center space-x-2 text-sm text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
            <span>Refresh</span>
          </button>
        </div>

        {error && (
          <div className="p-4 bg-red-50 dark:bg-red-900/20 border border-red-500 rounded-lg">
            <p className="text-sm text-red-700 dark:text-red-300">{error}</p>
          </div>
        )}

        {/* Workspace + members */}
        <section className="workspace-panel rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5">
          <div className="flex items-center space-x-2 mb-3">
            <Building2 className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            <h3 className="font-semibold text-gray-900 dark:text-white">
              {workspace?.name ?? 'Workspace'}
            </h3>
            {workspace?.role && (
              <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200">
                {workspace.role}
              </span>
            )}
          </div>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            slug: <code>{workspace?.slug ?? '—'}</code>
          </p>

          <div className="mt-4 flex items-center space-x-2">
            <Users className="w-4 h-4 text-gray-500 dark:text-gray-400" />
            <h4 className="text-sm font-medium text-gray-900 dark:text-white">
              Members ({members.length})
            </h4>
          </div>
          <ul className="mt-2 divide-y divide-gray-100 dark:divide-gray-700">
            {members.map((member) => (
              <li key={member.user_id} className="py-2 flex items-center justify-between text-sm">
                <span className="text-gray-900 dark:text-white">
                  {member.name ?? member.email}
                  <span className="ml-2 text-gray-400 dark:text-gray-500">{member.email}</span>
                </span>
                <span className="px-2 py-0.5 rounded-full text-xs bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200">
                  {member.role}
                </span>
              </li>
            ))}
            {members.length === 0 && (
              <li className="py-2 text-sm text-gray-400 dark:text-gray-500">No members found.</li>
            )}
          </ul>
        </section>

        {/* Projects */}
        <section className="workspace-panel rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5">
          <h3 className="font-semibold text-gray-900 dark:text-white mb-3">Projects</h3>

          {canCreateProject && (
            <div className="flex items-center space-x-2 mb-4">
              <input
                value={newProjectName}
                onChange={(event) => setNewProjectName(event.target.value)}
                placeholder="New project name"
                className="flex-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={() => void createProject()}
                disabled={busy || !newProjectName.trim()}
                className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-medium transition-colors disabled:cursor-not-allowed"
              >
                <FolderPlus className="w-4 h-4" />
                <span>Create</span>
              </button>
            </div>
          )}

          <ul className="divide-y divide-gray-100 dark:divide-gray-700">
            {projects.map((project) => (
              <li key={project.id} className="py-3 flex items-center justify-between">
                <div>
                  <div className="flex items-center space-x-2">
                    <span className="text-sm font-medium text-gray-900 dark:text-white">
                      {project.name}
                    </span>
                    {project.id === activeId && (
                      <span className="inline-flex items-center space-x-1 text-xs text-green-600 dark:text-green-400">
                        <Check className="w-3 h-3" />
                        <span>active</span>
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    <code>{project.slug}</code> · created {formatDate(project.created_at)}
                  </p>
                </div>
                <div className="flex items-center space-x-2">
                  {project.id !== activeId && (
                    <button
                      onClick={() => selectProject(project)}
                      className="px-3 py-1.5 rounded-md text-sm text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-700"
                    >
                      Use
                    </button>
                  )}
                  {canAdmin && (
                    <button
                      onClick={() => void archiveProject(project)}
                      disabled={busy}
                      title="Archive project"
                      className="p-2 rounded-md text-gray-500 hover:text-red-600 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </div>
              </li>
            ))}
            {projects.length === 0 && (
              <li className="py-2 text-sm text-gray-400 dark:text-gray-500">No projects yet.</li>
            )}
          </ul>
        </section>

        {/* API keys */}
        <section className="workspace-panel rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 p-5">
          <div className="flex items-center space-x-2 mb-3">
            <KeyRound className="w-5 h-5 text-gray-500 dark:text-gray-400" />
            <h3 className="font-semibold text-gray-900 dark:text-white">
              API keys{activeProject ? ` · ${activeProject.name}` : ''}
            </h3>
          </div>

          {!activeProject && (
            <p className="text-sm text-gray-400 dark:text-gray-500">
              Select a project to manage its API keys.
            </p>
          )}

          {activeProject && canAdmin && (
            <div className="flex items-center space-x-2 mb-4">
              <input
                value={newKeyName}
                onChange={(event) => setNewKeyName(event.target.value)}
                placeholder="Key name (e.g. ci-pipeline)"
                className="flex-1 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
              <button
                onClick={() => void createKey()}
                disabled={busy || !newKeyName.trim()}
                className="flex items-center space-x-2 px-4 py-2 rounded-lg bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white text-sm font-medium transition-colors disabled:cursor-not-allowed"
              >
                <KeyRound className="w-4 h-4" />
                <span>Create key</span>
              </button>
            </div>
          )}

          {freshKey && (
            <div className="mb-4 p-3 rounded-lg border border-green-500 bg-green-50 dark:bg-green-900/20">
              <p className="text-xs font-medium text-green-800 dark:text-green-200 mb-1">
                Copy this key now — it will not be shown again.
              </p>
              <code className="block break-all text-sm text-green-900 dark:text-green-100">
                {freshKey}
              </code>
            </div>
          )}

          {activeProject && (
            <ul className="divide-y divide-gray-100 dark:divide-gray-700">
              {keys.map((key) => (
                <li key={key.id} className="py-2 flex items-center justify-between text-sm">
                  <div>
                    <span className="text-gray-900 dark:text-white">{key.name}</span>
                    <span className="ml-2 text-gray-400 dark:text-gray-500">
                      <code>{key.prefix}…</code>
                    </span>
                    {key.revoked_at && (
                      <span className="ml-2 text-xs text-red-500">revoked</span>
                    )}
                  </div>
                  {!key.revoked_at && canAdmin && (
                    <button
                      onClick={() => void revokeKey(key.id)}
                      disabled={busy}
                      className="p-2 rounded-md text-gray-500 hover:text-red-600 hover:bg-gray-100 dark:hover:bg-gray-700 disabled:opacity-50"
                      title="Revoke key"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  )}
                </li>
              ))}
              {keys.length === 0 && (
                <li className="py-2 text-sm text-gray-400 dark:text-gray-500">No API keys yet.</li>
              )}
            </ul>
          )}
        </section>
      </div>
    </div>
  );
}

export default WorkspaceAdmin;
