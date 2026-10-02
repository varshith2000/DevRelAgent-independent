"use client";

import React, { useCallback, useEffect, useState } from 'react';
import { Building2, FolderCog, RefreshCw } from 'lucide-react';
import { apiFetch } from '../lib/api';
import {
  getIdentity,
  getProject,
  setIdentity,
  setProject,
  type Identity,
  type ProjectRef,
} from '../lib/auth';

interface Me {
  email: string | null;
  name: string | null;
  workspace_name: string;
  workspace_slug: string;
  role: string | null;
  project_id: string | null;
}

/**
 * Lets the user pick which project (within their workspace) requests are
 * scoped to. The choice is persisted and attached to every API call, so the
 * dashboard and chat follow the selection.
 */
export function ProjectSwitcher() {
  const [identity, setIdentityState] = useState<Identity>(getIdentity());
  const [projects, setProjects] = useState<ProjectRef[]>([]);
  const [active, setActive] = useState<ProjectRef | null>(null);
  const [role, setRole] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [meResponse, projectsResponse] = await Promise.all([
        apiFetch('/auth/me'),
        apiFetch('/projects'),
      ]);
      if (!meResponse.ok) throw new Error(`identity request failed (${meResponse.status})`);
      if (!projectsResponse.ok)
        throw new Error(`projects request failed (${projectsResponse.status})`);

      const me: Me = await meResponse.json();
      const list: ProjectRef[] = await projectsResponse.json();

      // Adopt the server-resolved identity so later requests match exactly what
      // the backend provisioned, even if localStorage was stale.
      const resolved: Identity = {
        email: me.email ?? identity.email,
        name: me.name ?? identity.name,
        workspace: me.workspace_slug,
      };
      setIdentityState(resolved);
      setIdentity(resolved);

      setProjects(list);
      setRole(me.role);

      const stored = getProject();
      const current =
        list.find((project) => project.id === stored?.id) ??
        list.find((project) => project.id === me.project_id) ??
        list[0] ??
        null;
      setActive(current);
      setProject(current);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load projects');
    } finally {
      setLoading(false);
    }
  }, [identity.email, identity.name]);

  useEffect(() => {
    void load();
    // Reload only when the workspace identity changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [identity.workspace]);

  const handleChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    const project = projects.find((item) => item.id === event.target.value) ?? null;
    setActive(project);
    setProject(project);
  };

  return (
    <div className="flex items-center space-x-2 rounded-lg border border-gray-200 dark:border-gray-700 bg-white dark:bg-gray-800 px-3 py-1.5">
      <Building2 className="w-4 h-4 text-gray-500 dark:text-gray-400" />
      <div className="flex flex-col leading-tight">
        <span className="text-xs text-gray-500 dark:text-gray-400">
          {identity.workspace}
          {role ? ` · ${role}` : ''}
        </span>
        <div className="flex items-center space-x-1">
          <FolderCog className="w-3.5 h-3.5 text-gray-400" />
          <select
            aria-label="Active project"
            value={active?.id ?? ''}
            onChange={handleChange}
            disabled={loading || projects.length === 0}
            className="bg-transparent text-sm font-medium text-gray-900 dark:text-white focus:outline-none disabled:opacity-60"
          >
            {projects.length === 0 && <option value="">No projects</option>}
            {projects.map((project) => (
              <option key={project.id} value={project.id}>
                {project.name}
              </option>
            ))}
          </select>
        </div>
      </div>
      <button
        onClick={() => void load()}
        title={error ?? 'Refresh projects'}
        className={`p-1 rounded transition-colors ${
          error
            ? 'text-red-500'
            : 'text-gray-400 hover:text-gray-900 dark:hover:text-white hover:bg-gray-100 dark:hover:bg-gray-700'
        }`}
      >
        <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
      </button>
    </div>
  );
}

export default ProjectSwitcher;
