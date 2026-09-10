#!/usr/bin/env bash
set -euo pipefail

ROOT="services/webhook-service"
fail() { echo "FAIL: $*" >&2; exit 1; }
[[ -d "$ROOT" ]] || fail "$ROOT is missing"

for dir in templates static public; do
  if find "$ROOT" -type d -name "$dir" -print -quit | grep -q .; then
    fail "forbidden UI directory found: $dir"
  fi
done
if find "$ROOT" -type f \( -name '*.html' -o -name '*.css' -o -name '*.jsx' -o -name '*.tsx' -o -name '*.vue' -o -name '*.svelte' \) -print -quit | grep -q .; then
  fail "forbidden UI file found"
fi
if find "$ROOT" -type f -name package.json -print -quit | grep -q .; then
  fail "package.json is not allowed under $ROOT"
fi
for file in "$ROOT"/go.mod "$ROOT"/go.sum "$ROOT"/sink/go.mod "$ROOT"/sink/go.sum; do
  [[ -f "$file" ]] || continue
  grep -qiE '(^|/)(react|vue|angular|svelte|next|nuxt|htmx)(/|@|$)|a-h/templ|gin-gonic/gin' "$file" && fail "UI framework reference in $file"
done
if grep -rl --include='*.go' 'html/template' "$ROOT" | grep -q .; then
  fail "html/template import found"
fi
if [[ -n "${BASE_REF:-}" ]]; then
  if git diff --name-only "$BASE_REF"...HEAD | grep -E '^frontend/' >/dev/null; then
    fail "frontend path changed in headless proof diff"
  fi
fi
echo "PASS: no forbidden UI directories"
echo "PASS: no browser UI file extensions"
echo "PASS: no package.json or UI framework dependencies"
echo "PASS: no html/template imports"
if [[ -n "${BASE_REF:-}" ]]; then echo "PASS: no frontend paths in diff"; else echo "PASS: frontend diff check skipped (BASE_REF empty)"; fi
