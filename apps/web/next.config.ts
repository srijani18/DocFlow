import path from "node:path";

import { loadEnvConfig } from "@next/env";
import type { NextConfig } from "next";

// One `.env` at the repo root serves both apps locally (see .env.example). On Vercel there
// is no such file and the dashboard's environment variables are used instead.
loadEnvConfig(path.resolve(__dirname, "../.."));

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
