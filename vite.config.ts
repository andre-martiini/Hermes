import path from "path";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { VitePWA } from "vite-plugin-pwa";

export default defineConfig(() => {
  return {
    server: {
      port: 3001,
      host: "0.0.0.0",
      proxy: {
        '/proxy-functions': {
          target: 'https://us-central1-gestao-hermes.cloudfunctions.net/',
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/proxy-functions/, ''),
          secure: false
        }
      }
    },
    plugins: [
      react(),
      VitePWA({
        registerType: "prompt",
        injectRegister: false,
        includeAssets: ["icon.svg"],
        manifest: {
          name: "Hermes - Gestão à Vista",
          short_name: "Hermes",
          description: "Gestão Inteligente de Tarefas e Metas",
          theme_color: "#0f172a",
          background_color: "#f8fafc",
          display: "standalone",
          icons: [
            {
              src: "icon.svg",
              sizes: "any",
              type: "image/svg+xml",
              purpose: "any maskable",
            },
          ],
          share_target: {
            action: "/_share-target",
            method: "POST",
            enctype: "multipart/form-data",
            params: {
              title: "title",
              text: "text",
              url: "url",
              files: [
                {
                  name: "audioFile",
                  accept: ["audio/*", "application/ogg", ".ogg"]
                },
                {
                  name: "videoFile",
                  accept: ["video/*", ".mp4", ".mov", ".mkv"]
                }
              ]
            }
          }
        },
        workbox: {
          clientsClaim: true,
          // Sem estas exclusões o service worker devolve o index.html do app
          // para QUALQUER rota da origem, sem tocar na rede — inclusive as do
          // servidor MCP e do OAuth. Foi o que quebrou a vinculação do conector:
          // a página de autorização chegava como a tela inicial do Hermes,
          // servida do cache, e nenhuma requisição saía do navegador.
          navigateFallbackDenylist: [
            /^\/__/,
            /^\/mcp(\/|$)/,
            /^\/oauth\//,
            /^\/\.well-known\//,
          ],
          maximumFileSizeToCacheInBytes: 4 * 1024 * 1024,
          importScripts: ["firebase-messaging-sw.js", "share-target-sw.js"],
          runtimeCaching: [
            {
              urlPattern: /^https:\/\/fonts\.googleapis\.com\/.*/i,
              handler: "CacheFirst",
              options: {
                cacheName: "google-fonts-cache",
                expiration: {
                  maxEntries: 10,
                  maxAgeSeconds: 60 * 60 * 24 * 365,
                },
                cacheableResponse: {
                  statuses: [0, 200],
                },
              },
            },
            {
              urlPattern: /^https:\/\/fonts\.gstatic\.com\/.*/i,
              handler: "CacheFirst",
              options: {
                cacheName: "gstatic-fonts-cache",
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
      }),
    ],
    resolve: {
      alias: {
        "@": path.resolve(__dirname, "."),
      },
    },
  };
});
