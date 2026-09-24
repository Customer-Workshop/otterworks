{{/*
Namespace the incident rules and dashboard are scoped to.
*/}}
{{- define "document-service.monitoringNamespace" -}}
{{- .Values.monitoring.namespaceLabel | default .Release.Namespace -}}
{{- end -}}

{{/*
Scope a PromQL expression to one namespace by adding a namespace matcher to
every otterworks_*, http_* and ALERTS selector. Selectors with braces get the
matcher prepended; bare metric names get a new brace block.
Usage: include "document-service.scopeExpr" (dict "expr" $expr "namespace" $ns)
*/}}
{{- define "document-service.scopeExpr" -}}
{{- $m := printf "namespace=%q" .namespace -}}
{{- $expr := regexReplaceAll `\b((?:http|otterworks)_[a-z0-9_]+|ALERTS)\{` .expr (printf "${1}{%s, " $m) -}}
{{- regexReplaceAll `\b((?:http|otterworks)_[a-z0-9_]+)\b([^{a-z0-9_]|$)` $expr (printf "${1}{%s}${2}" $m) -}}
{{- end -}}

{{/*
UID of the per-namespace incident dashboard (Grafana UIDs are limited to 40 chars).
*/}}
{{- define "document-service.dashboardUid" -}}
{{- .Values.monitoring.dashboard.uid | default (printf "ir-%s" .Release.Namespace) | trunc 40 | trimSuffix "-" -}}
{{- end -}}
