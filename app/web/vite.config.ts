/// <reference types="vitest/config" />
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  // three.js (the 3D loupe) is a deliberately large, lazy-loaded chunk — don't warn.
  build: { chunkSizeWarningLimit: 900 },
  server: {
    port: 5173,
    // In dev the API runs on :8000; proxy /api there so the client uses same-origin.
    proxy: { "/api": { target: "http://localhost:8000", rewrite: (p) => p.replace(/^\/api/, "") } },
  },
  test: {
    environment: "jsdom",
    setupFiles: ["./src/test/setup.ts"],
    css: false,
    clearMocks: true, // reset mock call history before each test (beforeEach re-sets impls)
  },
});
