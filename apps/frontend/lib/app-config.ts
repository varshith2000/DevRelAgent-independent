/**
 * Build-time switches for the frontend.
 *
 * Both values are inlined by Next.js at build time, so the static export for
 * GitHub Pages is compiled with `NEXT_PUBLIC_DEMO_MODE=true` and
 * `NEXT_PUBLIC_BASE_PATH=/<repo>` (see `.github/workflows/pages.yml`). A normal
 * build leaves both unset and talks to the real backend with no base path.
 */

/** True when the frontend is compiled as the backend-less demo site. */
export const DEMO_MODE = process.env.NEXT_PUBLIC_DEMO_MODE === 'true';

/**
 * Sub-path the app is served from. GitHub project pages live at
 * `https://<user>.github.io/<repo>/`, so the export is built with
 * `basePath=/<repo>`. Empty for local development and root deployments.
 */
export const BASE_PATH = (process.env.NEXT_PUBLIC_BASE_PATH ?? '').replace(/\/+$/, '');

/**
 * Prefix a root-relative path with the deployment base path.
 *
 * Next.js applies `basePath` to `next/link` and the router automatically, but
 * raw browser navigation (`<a href>`, `window.location.assign`,
 * `history.replaceState`) does not, so those call sites use this helper.
 */
export function withBasePath(path: string): string {
  if (!BASE_PATH) return path;
  return path === '/' ? `${BASE_PATH}/` : `${BASE_PATH}${path}`;
}
