"""Dynamic workflow: port the OtterWorks .NET WPF desktop client to Angular.

Shape:
  1. deterministic enumeration of clients/windows-desktop Views/*.xaml
  2. one prep/scaffold agent -> pushes a base branch with the Angular workspace,
     shell + router (a lazy route per screen), shared API service, token store,
     proxy config and test setup, so per-screen work is purely additive
  3. one analyze -> port chain per screen, run concurrently, each porting agent
     branching off the base branch and touching only its own component folder
  4. one integration agent: merge every screen branch, ng build + ng test,
     bring up the stack, drive Chrome through the WPF flow, screenshot each
     state, push the integration branch and open a single PR

Run it with the `run_workflow` tool, passing this file's absolute path as
`script_path`. Override the checkout it enumerates from with
WPF_MIGRATION_REPO_ROOT.
"""

import asyncio
import json
import os
import re
from pathlib import Path

REPO = "Cognition-Partner-Workshops/otterworks"
REPO_URL = f"https://github.com/{REPO}"
REPO_ROOT = Path(os.environ.get("WPF_MIGRATION_REPO_ROOT", "/home/ubuntu/repos/otterworks"))
RUN_ID = os.environ.get("WPF_MIGRATION_RUN_ID", "r20260926035840")

WPF_DIR = "clients/windows-desktop/OtterWorks.Desktop"
VIEWS_DIR = REPO_ROOT / WPF_DIR / "Views"
ANGULAR_APP = "frontend/desktop-client"

BASE_BRANCH = f"devin/{RUN_ID}-desktop-client-base"
INTEGRATION_BRANCH = f"devin/{RUN_ID}-desktop-client-angular"

# MainWindow.xaml is the WPF shell (chrome + navigation host), not a routed
# screen: the scaffold agent owns it as the Angular app shell.
SHELL_VIEWS = {"MainWindow"}

MODE = "fast"

COMMON = f"""\
Repository: {REPO_URL} (clone it; it is the OtterWorks monorepo).
Work only on branches; NEVER push to `main` and never open a PR unless told to.
`main` is the golden app: do not fix planted bugs outside your scope.
Do not name, credit or identify any person or requester in branches, commits, PR
titles or PR bodies.

Legacy source (the spec): `{WPF_DIR}` — a .NET Framework 4.8 WPF client (MVVM,
classic csproj, Newtonsoft.Json). Read `clients/windows-desktop/README.md` first.
Reference screenshots of the real app are in
`clients/windows-desktop/docs/screenshots/` — they are the behavioural spec.

Target: an Angular 17 + Angular Material app at `{ANGULAR_APP}`, mirroring
`frontend/admin-dashboard` (same Angular/Material major versions, standalone
components, `ng test` with ChromeHeadless via karma.conf.js, `proxy.conf.mjs`
proxying `/api` to the gateway at http://localhost:8080).

API contract (through the gateway, base path `/api/v1`, all non-auth calls send
`Authorization: Bearer <accessToken>`):
  POST /auth/register  {{displayName, email, password}} -> {{accessToken, refreshToken, tokenType, expiresIn, user}} (camelCase)
  POST /auth/login     {{email, password}}              -> same shape
  GET  /documents?page=&size=                           -> {{items, total, page, size, pages}} (snake_case)
  POST /documents      {{title}}                        -> created document (snake_case)
  GET  /files?page=&page_size=                          -> {{files, total, page, page_size}} (snake_case)
"""


def discover_screens():
    """Enumerate the WPF views deterministically from the checkout."""
    screens = []
    for xaml in sorted(VIEWS_DIR.glob("*.xaml")):
        name = xaml.stem
        if name in SHELL_VIEWS:
            continue
        slug = re.sub(r"View$", "", name)
        slug = re.sub(r"(?<!^)(?=[A-Z])", "-", slug).lower()
        screens.append(
            {
                "view": name,
                "slug": slug,
                "xaml": f"{WPF_DIR}/Views/{name}.xaml",
                "view_model": f"{WPF_DIR}/ViewModels/{re.sub(r'View$', '', name)}ViewModel.cs",
                "folder": f"{ANGULAR_APP}/src/app/pages/{slug}",
                "route": f"/{slug}",
                "selector": f"app-{slug}-page",
                "component_file": f"{ANGULAR_APP}/src/app/pages/{slug}/{slug}.component.ts",
                "class_name": "".join(p.capitalize() for p in slug.split("-")) + "Component",
                "branch": f"devin/{RUN_ID}-desktop-client-{slug}",
            }
        )
    return screens


SCREENS = discover_screens()
SCREEN_TABLE = json.dumps(SCREENS, indent=2, sort_keys=True)

PREP_SCHEMA = {
    "type": "object",
    "properties": {
        "branch": {"type": "string"},
        "assignments": {"type": "string"},
        "shared_files": {"type": "string"},
        "notes": {"type": "string"},
    },
    "required": ["branch", "assignments"],
}

ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "screen": {"type": "string"},
        "behaviours": {"type": "array", "items": {"type": "string"}},
        "api_calls": {"type": "array", "items": {"type": "string"}},
        "validation_rules": {"type": "array", "items": {"type": "string"}},
        "states": {"type": "array", "items": {"type": "string"}},
        "navigation": {"type": "string"},
    },
    "required": ["screen", "behaviours", "api_calls", "validation_rules", "states"],
}

PORT_SCHEMA = {
    "type": "object",
    "properties": {
        "screen": {"type": "string"},
        "branch": {"type": "string"},
        "files": {"type": "array", "items": {"type": "string"}},
        "specs": {"type": "string"},
        "not_ported": {"type": "string"},
    },
    "required": ["screen", "branch"],
}

INTEGRATION_SCHEMA = {
    "type": "object",
    "properties": {
        "branch": {"type": "string"},
        "pr_url": {"type": "string"},
        "build_and_test": {"type": "string"},
        "browser_verified": {"type": "boolean"},
        "screenshots": {"type": "array", "items": {"type": "string"}},
        "not_ported": {"type": "string"},
    },
    "required": ["branch", "pr_url", "build_and_test", "browser_verified"],
}

META = {
    "name": "dotnet-wpf-to-angular",
    "description": (
        "Port the OtterWorks .NET Framework 4.8 WPF desktop client to an Angular 17 app "
        "at frontend/desktop-client: scaffold once, port each WPF view concurrently on "
        "its own branch, then merge, test, browser-verify and open one PR."
    ),
    "product": "OtterWorks desktop client (clients/windows-desktop -> frontend/desktop-client)",
    "soft_time_limit_minutes": 30,
    "phases": [
        {
            "title": "scaffold",
            "detail": "Create the Angular workspace, shell, router, shared API service, token store, proxy and test setup on a base branch",
            "count": 1,
            "labels": ["scaffold"],
            "soft_time_limit_minutes": 45,
        },
        {
            "title": "analyze",
            "detail": "Read each WPF view + view model and report its behaviours, API calls, validation rules and states",
            "count": len(SCREENS),
            "labels": [f"analyze-{s['slug']}" for s in SCREENS],
            "soft_time_limit_minutes": 20,
        },
        {
            "title": "port",
            "detail": "Implement each screen as an Angular component inside its own folder, with Karma/Jasmine specs, on its own branch",
            "count": len(SCREENS),
            "labels": [f"port-{s['slug']}" for s in SCREENS],
            "soft_time_limit_minutes": 45,
        },
        {
            "title": "integrate",
            "detail": "Merge the screen branches, build, test, drive the real app in Chrome, screenshot each state and open one PR",
            "count": 1,
            "labels": ["integrate"],
            "soft_time_limit_minutes": 60,
        },
    ],
}


def prep_prompt():
    return f"""{COMMON}

TASK — scaffold the Angular desktop client (this is the foundation every other
agent builds on; their work must be purely additive on top of it).

1. Create a new Angular 17 workspace at `{ANGULAR_APP}`, copying the conventions of
   `frontend/admin-dashboard`: same Angular + Angular Material major versions
   (^17.3.0), standalone components, `angular.json` with build/test/serve targets,
   `karma.conf.js` using the `ChromeHeadlessNoSandbox` custom launcher,
   `tsconfig.json`/`tsconfig.spec.json` with the same strictness, `src/styles.scss`
   importing an Angular Material theme, and package.json scripts
   `start` (ng serve --port 4300), `build`, `test`
   (`ng test --watch=false --browsers=ChromeHeadless`), `lint`.
2. Add `proxy.conf.mjs` proxying `/api` to `process.env.API_GATEWAY_URL || "http://localhost:8080"`,
   wired into the `serve` target exactly as the admin dashboard does.
3. Port the WPF shell (`{WPF_DIR}/Views/MainWindow.xaml` +
   `ViewModels/MainViewModel.cs`) as the app shell component: the OtterWorks
   header bar (accent background, "OtterWorks Desktop" wordmark) and the
   "Signed in as <display name>" area, shown only when authenticated, with a
   `<router-outlet>` below it.
4. Declare the router in `src/app/app.routes.ts` with a LAZY route
   (`loadComponent: () => import(...)`) for EVERY screen listed below, plus a
   default redirect to `/login` and a wildcard redirect. Each lazy import must
   point at the component file listed for that screen and the component class
   name listed for it. Create each screen's folder with a minimal placeholder
   standalone component (correct selector, class name, `templateUrl`/inline
   template saying the screen is not ported yet) so the app builds before the
   per-screen agents land. Guard the authenticated routes with a functional
   auth guard that redirects to `/login`.
5. Implement the shared `OtterWorksApiService`
   (`{ANGULAR_APP}/src/app/core/services/otterworks-api.service.ts`) as a
   faithful port of `{WPF_DIR}/Services/OtterWorksApiClient.cs`: methods
   `register(displayName, email, password)`, `login(email, password)`,
   `getDocuments(page = 1, size = 50)`, `createDocument(title)`,
   `getFiles(page = 1, pageSize = 50)`; base URL `/api/v1`; the same error
   extraction behaviour (prefer `message`, then `error`, then `detail` from a
   JSON error body, else the raw body, else "Request failed with status N"),
   surfaced as a typed `ApiError`. Port the DTOs under
   `src/app/core/models/` keeping the exact wire field names (auth camelCase,
   document/file snake_case).
6. Implement the browser equivalent of `Services/SessionState.cs` as
   `src/app/core/services/session.service.ts`: holds accessToken, refreshToken
   and user, exposes `isAuthenticated` and the current user's display name (or
   email) as observable/signal state, `setSession()`, `clear()` and restore
   from `localStorage` on construction (the browser analogue of the DPAPI
   persisted session). Add an HTTP interceptor attaching
   `Authorization: Bearer <token>` to non-auth requests.
7. Add unit specs for the API service and session service, and make sure
   `npm install`, `npx ng build` and `npm test` (ChromeHeadless) all pass.
   Do not modify anything outside `{ANGULAR_APP}` except, if genuinely needed,
   a one-line mention in a top-level README.

Screens that need routes and folders (JSON):
{SCREEN_TABLE}

Push your work to the branch `{BASE_BRANCH}` (create it off the latest `main`,
commit, push). Do NOT open a pull request.

Report in structured output: `branch` (exactly `{BASE_BRANCH}`), `assignments`
(a compact per-screen list of route -> component folder -> selector -> class
name as you actually created them), `shared_files` (the shared files you created
that per-screen agents must NOT edit), and `notes`.
"""


def analyze_prompt(screen):
    return f"""{COMMON}

TASK — analysis only, write NO code and push nothing.

Read these files in the repository:
  - `{screen['xaml']}`
  - `{screen['view_model']}`
  - `{WPF_DIR}/ViewModels/MainViewModel.cs` (navigation context)
  - the reference screenshots in `clients/windows-desktop/docs/screenshots/`

Report exactly what the `{screen['view']}` screen does, precisely enough that
another engineer can reimplement it in Angular without reading the C#:
  - every user-visible behaviour and control, including button enable/disable logic
  - every API call it makes (method, path, request body, what it does with the response)
  - every validation rule (required fields, minimum lengths, trimming, etc.)
  - every state the screen can be in (initial, loading/busy, error, empty, populated,
    success) and what is rendered in each — the empty state matters
  - navigation into and out of the screen (including any link to another screen)

Structured output: `screen` = "{screen['view']}", `behaviours`, `api_calls`,
`validation_rules`, `states` (each an array of one-line strings), and
`navigation` (one short paragraph).
"""


def port_prompt(screen, analysis):
    return f"""{COMMON}

TASK — implement the `{screen['view']}` screen of the legacy WPF client as an
Angular component, and push it on its own branch.

Start from the existing branch `{BASE_BRANCH}` (already pushed): it contains the
Angular 17 workspace at `{ANGULAR_APP}` with the app shell, the router (a lazy
route for your screen is ALREADY declared), the shared
`OtterWorksApiService` (a port of `OtterWorksApiClient`), the session/token
service, the auth interceptor, the proxy config and the Karma test setup.
    git checkout -b {screen['branch']} origin/{BASE_BRANCH}

YOU OWN EXACTLY ONE DIRECTORY: `{screen['folder']}`.
Implement your screen there and nowhere else. Do NOT edit the router, the shared
services, the shell, package.json, or any other screen's folder — other agents
are working on this app concurrently and any edit outside your folder will
collide. Your component file must stay at `{screen['component_file']}`, exporting
the standalone component class `{screen['class_name']}` with selector
`{screen['selector']}` (the route `{screen['route']}` lazy-loads exactly that),
because the router already imports it under that path and name.
Use the shared `OtterWorksApiService` and session service from
`{ANGULAR_APP}/src/app/core/` — do not re-implement HTTP calls.
Use Angular Material components and reactive forms, matching the look of the
WPF screenshots and the conventions of `frontend/admin-dashboard`.

This is the analysis of the legacy screen you must reproduce (behaviours, API
calls, validation rules, states):
{json.dumps(analysis, indent=2, sort_keys=True)}

Also read `{screen['xaml']}` and `{screen['view_model']}` yourself, plus the
screenshots in `clients/windows-desktop/docs/screenshots/`, and reproduce every
state they show — including the empty state and any link to another screen.

Add Karma/Jasmine specs next to your component (`*.spec.ts`, inside your folder)
covering the behaviours and validation rules listed above, using
`HttpClientTestingModule`/spies rather than a live backend. Run
`npm install && npx ng test --watch=false --browsers=ChromeHeadless` and
`npx ng build` from `{ANGULAR_APP}` and make sure both pass before pushing.

Push to the branch `{screen['branch']}`. Do NOT open a pull request and do NOT
merge anything.

Structured output: `screen` = "{screen['view']}", `branch` (exactly
`{screen['branch']}`), `files` (the files you added), `specs` (one line on what
your specs cover), `not_ported` (anything from the legacy screen you left out,
or "none").
"""


def integration_prompt(ported, failed):
    branches = "\n".join(f"  - {p['screen']}: {p['branch']}" for p in ported)
    failures = "\n".join(f"  - {f}" for f in failed) or "  - none"
    shots = "\n".join(
        f"  {i}. {name}" for i, name in enumerate(
            [
                "register screen filled in",
                "documents list — empty state for the new account",
                "document created — it appears in the list",
                "files list",
                "logged out (back on the login screen)",
                "logged back in — the document persists",
            ],
            start=1,
        )
    )
    return f"""{COMMON}

TASK — integrate the ported screens, verify the app for real in a browser, and
open ONE pull request.

1. Create `{INTEGRATION_BRANCH}` from `origin/{BASE_BRANCH}` and merge every one
   of these screen branches into it (they were built to be additive — each agent
   only touched its own component folder, so conflicts should be trivial;
   resolve any that appear without dropping work):
{branches}
   Screens that failed to port (leave them as the scaffolded placeholder and
   list them in the PR as not ported):
{failures}

2. Make the app green from `{ANGULAR_APP}`:
   `npm install`, `npx ng build`, and
   `npx ng test --watch=false --browsers=ChromeHeadless`.
   Fix whatever is needed (inside `{ANGULAR_APP}`) to make both pass. Capture the
   tail of both outputs verbatim for the PR.

3. Bring up the real backend from the repo root (`make up`; `make infra-up`
   first if needed) and wait for `curl http://localhost:8080/health` to be
   healthy. Then start the Angular dev server (`npm start`, port 4300).

4. Drive the app in Chrome as a user, following the exact flow the WPF
   screenshots show, and take a screenshot of each state:
{shots}
   Use a fresh random email for the registration so the documents list really is
   empty. The final step must prove the document persisted across logout/login
   against the real backend. Save the screenshots under
   `{ANGULAR_APP}/docs/screenshots/` with those names (`01-...png` ... `06-...png`)
   and commit them.

5. Push `{INTEGRATION_BRANCH}` and open exactly ONE pull request into `main`
   titled for the migration (no person's name anywhere). The PR body must have:
   - a short summary of the port (what the Angular app is, where it lives, how to
     run it: `npm install && npm start`, proxying `/api` to the gateway);
   - a screen-by-screen WPF-vs-Angular comparison table embedding BOTH the
     existing legacy screenshots (`clients/windows-desktop/docs/screenshots/*.png`)
     and the new Angular ones (`{ANGULAR_APP}/docs/screenshots/*.png`) as
     markdown images, so a reviewer sees them side by side;
   - the `ng build` and `ng test` output;
   - a bullet list of anything NOT ported (including the failed screens above and
     anything the per-screen agents flagged).

Structured output: `branch` (exactly `{INTEGRATION_BRANCH}`), `pr_url`,
`build_and_test` (a short verdict plus the key numbers, e.g. specs executed /
failed), `browser_verified` (true only if you really drove the flow in Chrome
end to end against the live backend), `screenshots` (the committed paths), and
`not_ported`.
"""


async def main():
    await register_workflow(META)
    log(f"discovered {len(SCREENS)} WPF screens to port: " + ", ".join(s["view"] for s in SCREENS))
    if not SCREENS:
        raise RuntimeError(f"No WPF views found under {VIEWS_DIR}")

    log(f"scaffold stage starting; base branch {BASE_BRANCH}")
    prep = await agent(
        prep_prompt(),
        phase="scaffold",
        label="scaffold",
        schema=PREP_SCHEMA,
        mode=MODE,
        repos=[REPO],
        soft_time_limit_minutes=45,
    )
    log(f"scaffold done on {prep['branch']}: {prep['assignments'][:400]}")

    failed = []

    async def analyze(screen):
        try:
            result = await agent(
                analyze_prompt(screen),
                phase="analyze",
                label=f"analyze-{screen['slug']}",
                schema=ANALYZE_SCHEMA,
                mode=MODE,
                repos=[REPO],
                soft_time_limit_minutes=20,
            )
            log(f"analyze {screen['view']}: {len(result['behaviours'])} behaviours, {len(result['states'])} states")
            return {"screen": screen, "analysis": result}
        except WorkflowAgentError as exc:  # noqa: F821 (provided by the runtime shim)
            log(f"analyze FAILED for {screen['view']}: {exc}; skipping this screen")
            failed.append(f"{screen['view']} (analysis failed)")
            return {"screen": screen, "analysis": None}

    async def port(item):
        screen = item["screen"]
        if item["analysis"] is None:
            return None
        try:
            result = await agent(
                port_prompt(screen, item["analysis"]),
                phase="port",
                label=f"port-{screen['slug']}",
                schema=PORT_SCHEMA,
                mode=MODE,
                repos=[REPO],
                soft_time_limit_minutes=45,
            )
            log(f"ported {screen['view']} -> {result['branch']}")
            return result
        except WorkflowAgentError as exc:  # noqa: F821
            log(f"port FAILED for {screen['view']}: {exc}; recording and continuing")
            failed.append(f"{screen['view']} (port failed)")
            return None

    results = await pipeline(SCREENS, analyze, port)
    ported = [r for r in results if r]
    log(f"port stage complete: {len(ported)} ported, {len(failed)} failed ({failed or 'none'})")

    if not ported:
        raise RuntimeError("Every screen failed to port; nothing to integrate")

    integration = await agent(
        integration_prompt(ported, failed),
        phase="integrate",
        label="integrate",
        schema=INTEGRATION_SCHEMA,
        mode=MODE,
        repos=[REPO],
        soft_time_limit_minutes=60,
    )
    log(f"integration branch {integration['branch']} -> PR {integration['pr_url']}")
    log(f"build/test: {integration['build_and_test']}")
    log(f"browser verified: {integration['browser_verified']}")
    log("RESULT " + json.dumps({
        "base_branch": BASE_BRANCH,
        "integration_branch": integration["branch"],
        "pr_url": integration["pr_url"],
        "screens_ported": [p["screen"] for p in ported],
        "screens_failed": failed,
        "screenshots": integration.get("screenshots", []),
        "browser_verified": integration["browser_verified"],
        "build_and_test": integration["build_and_test"],
        "not_ported": integration.get("not_ported", ""),
    }, sort_keys=True))


asyncio.run(main())
