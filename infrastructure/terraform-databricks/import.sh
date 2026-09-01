#!/usr/bin/env bash
set -euo pipefail

imports=(
  'databricks_catalog.ow_tp|ow_tp'
  'databricks_schema.ow_tp_bronze|ow_tp.bronze'
  'databricks_schema.ow_tp_silver|ow_tp.silver'
  'databricks_schema.ow_tp_gold|ow_tp.gold'
  'databricks_volume.ow_tp_bronze_landing|ow_tp.bronze.landing'
  'databricks_secret_scope.ow_tp|ow_tp'
)

for item in "${imports[@]}"; do
  address=${item%%|*}
  object_id=${item#*|}
  if output=$(terraform import "$address" "$object_id" 2>&1); then
    printf '%s: imported\n' "$address"
  elif grep -Fq 'Resource already managed by Terraform' <<<"$output"; then
    printf '%s: already in state\n' "$address"
  elif grep -Fq 'Cannot import non-existent remote object' <<<"$output"; then
    printf '%s: not found (plan will create)\n' "$address"
  else
    printf '%s\n' "$output" >&2
    exit 1
  fi
done
