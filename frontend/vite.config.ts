import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import tailwindcss from '@tailwindcss/vite';
import { compression } from 'vite-plugin-compression2';

export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    // Brotli compression for static assets (smaller than gzip)
    compression({
      algorithm: 'brotliCompress',
      exclude: [/\.(br)$/, /\.(gz)$/, /\.(png|jpe?g|gif|webp|avif)$/],
      threshold: 1024,
    }),
    // Gzip fallback
    compression({
      algorithm: 'gzip',
      exclude: [/\.(br)$/, /\.(gz)$/, /\.(png|jpe?g|gif|webp|avif)$/],
      threshold: 1024,
    }),
  ],

  server: {
    host: '0.0.0.0',
    port: 5173,
  },

  build: {
    // Enable CSS code splitting
    cssCodeSplit: true,
    // Generate sourcemaps only in production for debugging
    sourcemap: false,
    // Minify with esbuild (fastest) for production
    minify: 'esbuild',
    // Chunk size warnings at 500kB
    chunkSizeWarningLimit: 500,
    rollupOptions: {
      output: {
        // Manual chunk splitting for optimal caching
        manualChunks(id: string) {
          // React core libraries
          if (id.includes('node_modules/react-dom') || id.includes('node_modules/react/') || id.includes('node_modules/react-router')) {
            return 'react-vendor';
          }
          // State management
          if (id.includes('node_modules/zustand')) {
            return 'data-vendor';
          }
          // UI icons
          if (id.includes('node_modules/lucide-react')) {
            return 'icons';
          }
          // Markdown rendering (heavy)
          if (id.includes('node_modules/react-markdown') || id.includes('node_modules/remark-gfm')) {
            return 'markdown';
          }
        },
      },
    },
  },
});
