// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - tanstackStart, viteReact, tailwindcss, tsConfigPaths, nitro (build-only using cloudflare as a default target),
//     componentTagger (dev-only), VITE_* env injection, @ path alias, React/TanStack dedupe,
//     error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";
import netlify from "@netlify/vite-plugin-tanstack-start";

// Local dev can opt out of the Netlify plugin (which resolves netlify.toml's
// `base = "frontend"` incorrectly when run from the frontend/ cwd) via
// VITE_DISABLE_NETLIFY=true. Production/Netlify builds leave it enabled.
const netlifyPlugins = process.env.VITE_DISABLE_NETLIFY === "true" ? [] : [netlify()];

export default defineConfig({
  plugins: netlifyPlugins,
  vite: {
    preview: {
      // Required when serving via `npm start` (vite preview) on Render.
      allowedHosts: [".onrender.com", "astro-chart-web.onrender.com"],
    },
  },
});
