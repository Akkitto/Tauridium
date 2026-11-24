import { defineConfig } from "vitest/config";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Tauri-recommended Vite setup: fixed port, preserve console output, ignore src-tauri.
const host = process.env.TAURI_DEV_HOST;

export default defineConfig({
  plugins: [svelte()],
  clearScreen: false,
  // Use Svelte client entry points for rune tests running under Vitest in Node.
  resolve: process.env.VITEST ? { conditions: ["browser"] } : undefined,
  test: {
    include: ["src/**/*.test.ts"],
  },
  server: {
    port: 1420,
    strictPort: true,
    host: host || false,
    hmr: host ? { protocol: "ws", host, port: 1421 } : undefined,
    watch: { ignored: ["**/src-tauri/**"] },
  },
});
