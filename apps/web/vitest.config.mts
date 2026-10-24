import react from "@vitejs/plugin-react";
import tsconfigPaths from "vite-tsconfig-paths";
import { defineConfig } from "vitest/config";

export default defineConfig({
  plugins: [tsconfigPaths(), react()],
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./vitest.setup.ts"],
    include: ["src/**/*.test.{ts,tsx}"],
    env: {
      NEXT_PUBLIC_API_BASE_URL: "http://api.test",
      NEXT_PUBLIC_SUPABASE_URL: "http://supabase.test",
      NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY: "sb_publishable_test",
    },
    clearMocks: true,
    restoreMocks: true,
  },
});
