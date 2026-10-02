/**
 * Single source of truth for the backend API base URL.
 *
 * Configure with NEXT_PUBLIC_API_URL (e.g. https://api.example.com).
 * Falls back to the local dev server so `npm run dev` works out of the box.
 */
export const API_BASE_URL: string =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/+$/, '') || 'http://localhost:8000';

/** Build an absolute backend URL from a path such as `/chat`. */
export function apiUrl(path: string): string {
  const normalized = path.startsWith('/') ? path : `/${path}`;
  return `${API_BASE_URL}${normalized}`;
}
