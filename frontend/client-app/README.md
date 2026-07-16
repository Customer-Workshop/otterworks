# OtterWorks Web App

React 18 single-page application built with Vite, served by nginx in production, and
wrapped by Capacitor to produce the native Android and iOS apps from the same codebase.

## Development

```bash
npm ci
npm run dev        # Vite dev server on http://localhost:3000
```

API calls to `/api/v1/*` are proxied to the API gateway (default `http://localhost:8080`,
override with `API_GATEWAY_URL`) so the browser only ever talks same-origin. In production
the nginx config (`nginx/default.conf.template`) performs the same proxying; the gateway
URL is substituted from the `API_GATEWAY_URL` env var at container start.

| Command | Purpose |
|---------|---------|
| `npm run dev` | Dev server with HMR (port 3000) |
| `npm run build` | Type-check (`tsc --noEmit`) + production build to `dist/` |
| `npm run lint` | ESLint |
| `npm test` | Vitest unit tests |
| `npm run test:e2e` | Playwright e2e (expects the backend stack running) |
| `npm run test:bdd` | Cucumber BDD suite |

Build-time env vars (Vite): `VITE_COLLAB_WS_URL` (collab websocket URL, default
`ws://localhost:8085`), `VITE_API_BASE_URL` (native builds only, see below).

## Docker

```bash
docker build -t otterworks-web-app .
docker run -p 3000:3000 -e API_GATEWAY_URL=http://api-gateway:8080 otterworks-web-app
```

The image is nginx (unprivileged, uid 101) serving `dist/` on port 3000 with an
`/api/health` endpoint and the `/api/v1` reverse proxy. When running with a read-only
root filesystem, mount a writable tmpfs at `/etc/nginx/conf.d` so the entrypoint can
render the config template (see `docker-compose.yml`).

## Mobile (Capacitor)

The `mobile/android/` and `mobile/ios/` directories are Capacitor platform projects
generated around the same `dist/` bundle (locations set via `android.path` / `ios.path`
in `capacitor.config.ts`). After changing web code:

```bash
npm run build && npx cap sync
npx cap run android   # build & launch on an Android emulator/device
npx cap open ios      # open in Xcode to run on an iOS simulator/device
```

Native builds cannot use the same-origin `/api/v1` proxy, so they call the API gateway
directly. Defaults target local development:

- Android emulator: `http://10.0.2.2:8080/api/v1` (host alias; cleartext is permitted via
  `android:usesCleartextTraffic` and `allowMixedContent` for dev only)
- Override at build time for other environments, e.g.
  `VITE_API_BASE_URL=https://api.example.com/api/v1 npm run build && npx cap sync`
- iOS simulator: use `VITE_API_BASE_URL=http://localhost:8080/api/v1`

The API gateway's default CORS config allows the Capacitor WebView origins
(`https://localhost` on Android, `capacitor://localhost` on iOS).

Auth tokens are kept in `localStorage` (WebView-local). If shipping to stores, consider
moving them to `@capacitor/preferences` or a secure-storage plugin, and add real app
icons/splash screens with `@capacitor/assets`.
