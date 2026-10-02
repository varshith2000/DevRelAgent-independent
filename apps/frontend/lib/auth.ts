/**
 * Client-side identity and project selection.
 *
 * The backend authenticates with `X-Dev-User-*` and `X-Project-*` headers while
 * AUTH_PROVIDER=dev. Until the Clerk sign-in flow lands, the UI keeps the
 * caller's chosen identity/workspace and active project in localStorage and
 * attaches them to every request.
 *
 * All reads are guarded so importing this module on the server is harmless.
 */

export interface Identity {
  email: string;
  name: string;
  workspace: string;
}

export interface ProjectRef {
  id: string;
  name: string;
  slug: string;
}

export const DEFAULT_IDENTITY: Identity = {
  email: 'dev@localhost',
  name: 'Dev User',
  workspace: 'dev-workspace',
};

const IDENTITY_KEY = 'devrelagent.identity';
const PROJECT_KEY = 'devrelagent.project';

/** Fired on window whenever the identity or project changes. */
export const IDENTITY_EVENT = 'devrelagent:identity-changed';

function isBrowser(): boolean {
  return typeof window !== 'undefined';
}

export function getIdentity(): Identity {
  if (!isBrowser()) return DEFAULT_IDENTITY;
  try {
    const raw = window.localStorage.getItem(IDENTITY_KEY);
    if (raw) return { ...DEFAULT_IDENTITY, ...(JSON.parse(raw) as Partial<Identity>) };
  } catch {
    // Corrupt value: fall back to the default identity.
  }
  return DEFAULT_IDENTITY;
}

export function setIdentity(identity: Partial<Identity>): Identity {
  const next = { ...getIdentity(), ...identity };
  if (isBrowser()) {
    window.localStorage.setItem(IDENTITY_KEY, JSON.stringify(next));
    window.dispatchEvent(new Event(IDENTITY_EVENT));
  }
  return next;
}

export function getProject(): ProjectRef | null {
  if (!isBrowser()) return null;
  try {
    const raw = window.localStorage.getItem(PROJECT_KEY);
    return raw ? (JSON.parse(raw) as ProjectRef) : null;
  } catch {
    return null;
  }
}

export function setProject(project: ProjectRef | null): void {
  if (!isBrowser()) return;
  if (project) {
    window.localStorage.setItem(PROJECT_KEY, JSON.stringify(project));
  } else {
    window.localStorage.removeItem(PROJECT_KEY);
  }
  window.dispatchEvent(new Event(IDENTITY_EVENT));
}

/** Headers identifying the caller (development auth provider). */
export function authHeaders(): Record<string, string> {
  const identity = getIdentity();
  return {
    'X-Dev-User-Email': identity.email,
    'X-Dev-User-Name': identity.name,
    'X-Dev-Workspace': identity.workspace,
  };
}

/** Headers selecting the active project, when one is chosen. */
export function projectHeaders(): Record<string, string> {
  const project = getProject();
  return project ? { 'X-Project-Id': project.id } : {};
}

/** Identity parameters for URLs that cannot carry headers (EventSource). */
export function authQueryParams(): Record<string, string> {
  const identity = getIdentity();
  const project = getProject();
  const params: Record<string, string> = {
    dev_user_email: identity.email,
    dev_user_name: identity.name,
    dev_workspace: identity.workspace,
  };
  if (project) params.project_id = project.id;
  return params;
}
