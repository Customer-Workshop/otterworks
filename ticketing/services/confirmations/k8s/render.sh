#!/usr/bin/env bash
# Render every manifest in this directory for one run: ./render.sh <token> <image> | kubectl apply -f -
set -euo pipefail
[[ $# -eq 2 ]] || { echo "usage: $0 <token> <image>" >&2; exit 2; }
[[ "$1" =~ ^tkt[a-z0-9]{1,12}$ ]] || { echo "bad token $1" >&2; exit 2; }
dir="$(cd "$(dirname "$0")" && pwd)"
for f in "$dir"/*.yaml; do
  echo "---"
  TOKEN="$1" IMAGE="$2" envsubst '${TOKEN} ${IMAGE}' < "$f"
done
