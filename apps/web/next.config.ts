import { existsSync } from "node:fs";
import path from "node:path";

import type { NextConfig } from "next";

// One `.env` at the repo root serves both apps locally (see .env.example). Variables that
// are already set win, so Vercel's dashboard values are never overridden; on Vercel the
// file doesn't exist at all.
const rootEnvFile = path.resolve(__dirname, "../../.env");
if (existsSync(rootEnvFile)) {
  process.loadEnvFile(rootEnvFile);
}

const nextConfig: NextConfig = {
  cacheComponents: true,
  partialPrefetching: true,
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
