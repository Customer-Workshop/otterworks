#!/usr/bin/env bash
# Redaction check over every ticketing deliverable (files, branch names, commit messages).
# Fails on credential-shaped strings, real-looking e-mail domains, internal identities, and
# any extra terms passed via REDACT_TERMS (comma-separated, case-insensitive), e.g. the request id
# and the requester's name.   usage: redaction-check.sh [path...]   (default: ticketing/)
source "$(dirname "$0")/lib.sh"
cd "${REPO_ROOT}" || exit 3
paths=("$@"); [ ${#paths[@]} -eq 0 ] && paths=(ticketing)
fail=0
check() { # label, regex [allow-regex]
  local hits rc=0
  hits="$(rg -n -i --hidden -g '!**/target/**' -g '!**/.runs/**' -g '!**/*.png' -e "$2" -- "${paths[@]}")" || rc=$?
  [ "${rc}" -gt 1 ] && die "rg failed on pattern for ${1}" 3
  [ -n "${3:-}" ] && hits="$(printf '%s\n' "${hits}" | rg -v -i -e "$3" || true)"
  hits="$(printf '%s\n' "${hits}" | sed '/^$/d' | head -20)"
  if [ -n "${hits}" ]; then echo "FAIL ${1}:"; echo "${hits}" | sed 's/^/    /'; fail=1; else echo "ok   ${1}"; fi
}
check "AWS access keys"            'AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}'
check "private keys"               '-----BEGIN [A-Z ]*PRIVATE KEY-----'
check "API tokens"                 '(cog_[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|gho_[A-Za-z0-9]{30,}|xox[bpa]-[A-Za-z0-9-]{10,}|sk-[A-Za-z0-9]{32,})'
check "non-synthetic e-mail"       '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[a-z]{2,}' '@(example\.(test|com|org)|users\.noreply\.github\.com)\b'
check "internal identity strings"  'google-oauth2\||Devin-PartnerWorkshops-[A-Za-z]+'
IFS=',' read -r -a extra <<< "${REDACT_TERMS:-}"
for t in "${extra[@]}"; do [ -n "${t}" ] && check "term '${t}'" "\\b${t}\\b"; done
echo "-- branch names and commit messages"
refs="$(git ls-remote --heads origin 'tkt/*' 'review-base-ticketing' | awk '{print $2}')"
msgs="$(git log --format='%s%n%b' origin/main..HEAD -- ticketing Makefile 2>/dev/null || true)"
for t in "${extra[@]}"; do
  [ -z "${t}" ] && continue
  if printf '%s\n%s\n' "${refs}" "${msgs}" | rg -q -i "\\b${t}\\b"; then echo "FAIL git metadata contains '${t}'"; fail=1; fi
done
if [ "${fail}" = 0 ]; then echo "PASS redaction check (${paths[*]})"; else echo "FAIL redaction check"; exit 1; fi
