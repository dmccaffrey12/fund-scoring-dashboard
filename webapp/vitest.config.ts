import { defineConfig } from "vitest/config";
import path from "path";

export default defineConfig({
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "client", "src"),
      "@shared": path.resolve(__dirname, "shared"),
    },
  },
  test: {
    globals: true,
    environment: "node",
    include: ["server/**/*.test.ts", "client/**/*.test.{ts,tsx}"],
    env: {
      DATABASE_PATH: "test_data.db",
    },
  },
});
