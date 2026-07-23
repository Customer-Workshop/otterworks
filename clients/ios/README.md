# OtterWorks iOS

A native **iOS client** for the OtterWorks platform, built with **Swift** and
**SwiftUI** (MVVM). It talks to the OtterWorks REST API through the API gateway using
`URLSession` and Swift concurrency (`async`/`await`).

It mirrors the core flow of the [`clients/windows-desktop`](../windows-desktop) client and
the `frontend/web-app` React client, against the same API contract.

## Features

- **Register** — display name, email, password → `POST /auth/register`
- **Login** — email, password → `POST /auth/login`, with a link between the two screens
- **Documents list** — `GET /documents` (Bearer token), with a friendly empty state
- **Create document** — a *New* box → `POST /documents { title }` → list refreshes
- **Files list** — `GET /files` (nice-to-have)
- **Logout** — clears the token and returns to the login screen

The JWT access token is held **in memory**. When `OTTERWORKS_PERSIST_TOKENS` is `true`
(the default) it is also stored in the iOS **Keychain** (`kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly`)
and restored on next launch. Tokens are never written to disk in plaintext.

## Project layout

```
clients/ios/
├── OtterWorks.xcodeproj/              # Xcode 16 project (file-system synchronized group)
├── project.yml                       # optional XcodeGen spec to regenerate the project
├── README.md
└── OtterWorks/
    ├── OtterWorksApp.swift            # @main App: builds SessionStore + API client, DI root
    ├── Info.plist                     # ATS localhost exception + configurable base URL
    ├── Assets.xcassets/               # AppIcon + AccentColor
    ├── Models/                        # Auth (camelCase) + Document/File (snake_case) DTOs
    ├── Services/                      # AppSettings, SessionStore (Keychain), APIError, API client
    ├── ViewModels/                    # Auth (login/register) + Documents view models
    └── Views/                         # Root shell, Login, Register, Documents (SwiftUI)
```

## Prerequisites

- **macOS** with **Xcode 16 or newer** (the project uses a file-system synchronized
  group, `objectVersion = 77`). On older Xcode, regenerate the project from `project.yml`
  with [XcodeGen](https://github.com/yonaskolb/XcodeGen) — see [Build](#build).
- The **iOS 17+ SDK / Simulator** (bundled with Xcode).
- No third-party dependencies — the app uses only `Foundation`, `SwiftUI`, and `Security`
  (Keychain).

## Configuration

The backend base URL and token persistence are read from `OtterWorks/Info.plist`
(analogous to `appsettings.json` in the Windows client):

| Info.plist key             | Default                           | Meaning                                   |
|----------------------------|-----------------------------------|-------------------------------------------|
| `OTTERWORKS_API_BASE_URL`  | `http://localhost:8080/api/v1`    | OtterWorks API gateway base URL           |
| `OTTERWORKS_PERSIST_TOKENS`| `true`                            | Persist the session token in the Keychain |

> **App Transport Security:** the plist enables `NSAllowsLocalNetworking` so the default
> `http://localhost` gateway works during local development. Point `OTTERWORKS_API_BASE_URL`
> at an `https` gateway for any non-local use.

> **Simulator networking:** the iOS Simulator shares the host's network, so
> `http://localhost:8080` reaches a gateway running via Docker Compose on your Mac. On a
> **physical device**, set `OTTERWORKS_API_BASE_URL` to your Mac's LAN IP (e.g.
> `http://192.168.1.20:8080/api/v1`).

## Running the backend

From the repository root (LocalStack emulates AWS — no cloud needed):

```bash
make infra-up && make up
# or, without make:
docker compose -f docker-compose.infra.yml -f docker-compose.yml up -d --build
```

Verify it is healthy:

```bash
curl http://localhost:8080/health      # -> {"status":"healthy",...}
```

## Build

Open the project in Xcode and run on a simulator:

```bash
open clients/ios/OtterWorks.xcodeproj
# then select an iPhone simulator and press Run (⌘R)
```

Or from the command line:

```bash
cd clients/ios
xcodebuild -project OtterWorks.xcodeproj -scheme OtterWorks \
  -destination 'platform=iOS Simulator,name=iPhone 16' build
```

**Regenerate the project (older Xcode / merge conflicts):**

```bash
brew install xcodegen        # once
cd clients/ios && xcodegen generate
```

## End-to-end flow

1. **Register** a new user (display name, email, password ≥ 8 chars).
2. You land on the **Documents** list — empty for a new account.
3. Type a title and tap **New** — the document appears in the list.
4. Tap **Log out**, then **Sign in** with the same credentials — the document is still
   there, proving it was persisted by the real backend.

## API contract used

Base URL: `http://localhost:8080/api/v1`. All non-auth calls send `Authorization: Bearer
<accessToken>`.

| Method & path         | Request                              | Response (shape)                                        |
|-----------------------|--------------------------------------|---------------------------------------------------------|
| `POST /auth/register` | `{ displayName, email, password }`   | `{ accessToken, refreshToken, tokenType, expiresIn, user }` (camelCase) |
| `POST /auth/login`    | `{ email, password }`                | same as register                                        |
| `GET /documents`      | query `page`, `size`                 | `{ items:[…], total, page, size, pages }` (snake_case)  |
| `POST /documents`     | `{ title }`                          | created document object (snake_case)                    |
| `GET /files`          | query `page`, `page_size`            | `{ files:[…], total, page, page_size }` (snake_case)    |

Auth payloads are camelCase while document/file payloads are snake_case; the client keeps
two `JSONEncoder`/`JSONDecoder` configurations (`.convertToSnakeCase` /
`.convertFromSnakeCase`) and selects the right one per call.
