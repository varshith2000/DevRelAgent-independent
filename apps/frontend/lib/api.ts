/**
 * Single source of truth for talking to the backend API.
 *
 * Configure with NEXT_PUBLIC_API_URL (e.g. https://api.example.com).
 * Falls back to the local dev server so `npm run dev` works out of the box.
 */

import { DEMO_MODE } from './app-config';
import { authHeaders, authQueryParams, projectHeaders } from './auth';

export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, '') || 'http://localhost:8000';

/** Build an absolute backend URL from a path such as `/chat`. */
export function apiUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalized}`;
}

/**
 * Build a backend URL for clients that cannot set headers (EventSource), by
 * moving the identity and project selection into query parameters.
 */
export function authUrl(path: string): string {
  const url = new URL(apiUrl(path));
  for (const [key, value] of Object.entries(authQueryParams())) {
    url.searchParams.set(key, value);
  }
  return url.toString();
}

/**
 * `fetch` against the backend with the caller's identity and project attached.
 *
 * In the static demo build there is no backend, so requests are answered from
 * the checked-in fixtures instead (see `lib/demo.ts`).
 */
export async function apiFetch(path: string, init: RequestInit = {}): Promise<Response> {
  if (DEMO_MODE) {
    const { demoFetch } = await import('./demo');
    return demoFetch(path, init);
  }

  const headers = new Headers(init.headers);
  for (const [key, value] of Object.entries({ ...authHeaders(), ...projectHeaders() })) {
    if (!headers.has(key)) headers.set(key, value);
  }
  return fetch(apiUrl(path), { ...init, headers });
}
