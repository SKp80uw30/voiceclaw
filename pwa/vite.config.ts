import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { VitePWA } from 'vite-plugin-pwa'

const pwaPlugin = VitePWA({
  registerType: 'prompt',
  manifest: {
    name: 'VoiceClaw',
    short_name: 'VoiceClaw',
    description: 'Voice-first AI agent',
    theme_color: '#0f172a',
    background_color: '#0f172a',
    display: 'standalone',
    orientation: 'portrait',
    start_url: '/',
    icons: [
      {
        src: '/icon-192.svg',
        sizes: '192x192',
        type: 'image/svg+xml',
      },
      {
        src: '/icon-512.svg',
        sizes: '512x512',
        type: 'image/svg+xml',
      },
    ],
  },
  workbox: {
    globPatterns: ['**/*.{js,css,html,ico,png,svg,woff2}'],
    runtimeCaching: [
      {
        urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
        handler: 'CacheFirst',
        options: {
          cacheName: 'google-fonts-cache',
          expiration: {
            maxEntries: 10,
            maxAgeSeconds: 60 * 60 * 24 * 365,
          },
          cacheableResponse: {
            statuses: [0, 200],
          },
        },
      },
    ],
  },
})

export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    ...(mode === 'production' ? [pwaPlugin] : []),
  ],
  optimizeDeps: {
    include: [
      '@pipecat-ai/client-js',
      '@pipecat-ai/client-react',
      '@pipecat-ai/small-webrtc-transport',
      '@pipecat-ai/voice-ui-kit',
      '@daily-co/daily-js',
    ],
  },
  server: {
    port: 5173,
    host: true,
    proxy: {
      '/offer': 'http://localhost:8000',
      '/state': 'http://localhost:8000',
    },
  },
}))
