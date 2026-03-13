#!/usr/bin/env node
const fs = require('fs');
const path = require('path');

const shimPath = path.join(__dirname, '..', 'node_modules', '@tailwindcss', 'vite', 'dist', 'index.mjs');
const shimContent = `// No-op shim: Tailwind CSS is handled by PostCSS instead
export default function tailwindcss() {
  return [
    { name: "@tailwindcss/vite:scan" },
    { name: "@tailwindcss/vite:generate:serve" },
    { name: "@tailwindcss/vite:generate:build" }
  ];
}
`;

try {
  fs.writeFileSync(shimPath, shimContent);
  console.log('[patch] @tailwindcss/vite replaced with no-op shim (PostCSS handles CSS)');
} catch (e) {
  console.warn('[patch] Could not patch @tailwindcss/vite:', e.message);
}
