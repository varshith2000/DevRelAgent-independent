import type { NextConfig } from "next";

/**
 * Static demo build switch.
 *
 * `NEXT_PUBLIC_DEMO_MODE=true` compiles the frontend as the backend-less demo
 * site (fixtures instead of API calls) and as a fully static bundle: `next
 * build` then emits `out/`, which `.github/workflows/pages.yml` uploads to
 * GitHub Pages. `NEXT_PUBLIC_BASE_PATH` must match the Pages sub-path
 * (for a project page, `/<repository-name>`).
 *
 * A normal build leaves both unset, stays server-rendered, and is unchanged.
 */
const demoMode = process.env.NEXT_PUBLIC_DEMO_MODE === "true";
const basePath = (process.env.NEXT_PUBLIC_BASE_PATH ?? "").replace(/\/+$/, "");

const nextConfig: NextConfig = {
  ...(demoMode
    ? {
        output: "export" as const,
        // Emit `route/index.html` so static hosting resolves nested routes.
        trailingSlash: true,
        // No image optimisation server exists on a static host.
        images: { unoptimized: true },
      }
    : {}),
  ...(demoMode && basePath ? { basePath } : {}),
};

export default nextConfig;
