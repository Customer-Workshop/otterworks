#!/usr/bin/env bash
# Fails if anything UI-shaped lands in the webhook service: HTML/CSS/JS/templates,
# static/public/asset directories, frontend toolchain files, or Go code that
# serves files or renders templates. The service is API-only; keep it that way.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail=0
report() { echo "::error::headless-guard: $*"; fail=1; }

# Tracked-or-untracked files, minus scripts/ (this guard) and go.sum.
files() {
  if git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git ls-files --cached --others --exclude-standard -- . | sed 's#^#./#'
  else
    find . -type f
  fi
}

mapfile -t ALL < <(files)

# 1. Forbidden extensions.
forbidden_ext='\.(html?|xhtml|css|scss|sass|less|js|jsx|mjs|cjs|ts|tsx|vue|svelte|tmpl|tpl|gohtml|gotmpl|hbs|mustache|ejs|pug|jade|njk|twig|jinja2?|j2|erb|haml|slim|svg|png|jpe?g|gif|webp|ico|woff2?|ttf|eot|otf|wasm)$'
for f in "${ALL[@]}"; do
  if [[ "$f" =~ $forbidden_ext ]]; then
    report "UI/static file present: $f"
  fi
done

# 2. Forbidden directory names anywhere in the tree.
forbidden_dir='(^|/)(static|public|assets?|templates?|views?|ui|web|www|frontend|client|dist|build|node_modules|pages|components|styles|layouts|partials)(/|$)'
for f in "${ALL[@]}"; do
  rel="${f#./}"
  if [[ "$(dirname "$rel")" =~ $forbidden_dir ]]; then
    report "UI-shaped directory: $rel"
  fi
done

# 3. Frontend toolchain / markup config files.
for f in "${ALL[@]}"; do
  base="$(basename "$f")"
  case "$base" in
    package.json|package-lock.json|yarn.lock|pnpm-lock.yaml|webpack.config.*|vite.config.*|tailwind.config.*|postcss.config.*|tsconfig.json|index.htm*)
      report "frontend toolchain file: $f" ;;
  esac
done

# 4. Go code that serves files or templates, or emits HTML content types.
go_patterns=(
  'html/template'
  'text/template'
  'http\.FileServer'
  'http\.ServeFile'
  'http\.ServeContent'
  'http\.Dir\('
  'http\.FS\('
  'embed\.FS'
  '//go:embed'
  'text/html'
  'application/xhtml'
  'text/css'
  'application/javascript'
  'text/javascript'
  'ExecuteTemplate'
  'ParseFiles'
  'ParseGlob'
  '<!DOCTYPE'
  '<html'
  '<script'
  '<body'
)
for pat in "${go_patterns[@]}"; do
  # Allow test files to *assert* these strings never appear.
  if hits=$(grep -rnE --include='*.go' --exclude='*_test.go' -- "$pat" . 2>/dev/null); then
    while IFS= read -r line; do report "forbidden pattern '$pat': $line"; done <<<"$hits"
  fi
done

if [[ $fail -ne 0 ]]; then
  echo "headless-guard: FAILED - webhook-service must stay API-only (JSON, no UI/static/templates)."
  exit 1
fi
echo "headless-guard: OK - no HTML, static assets, templates, or frontend tooling found."
