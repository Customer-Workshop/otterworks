{{/* Db2 database name: explicit dbName, else upper(run[0:7]) + B|A from the token (CONTRACTS.md §3.2). */}}
{{- define "db2-archive.dbName" -}}
{{- if .Values.dbName -}}
{{- .Values.dbName -}}
{{- else -}}
{{- $tok := required "namespaceToken (e.g. d24-after) or dbName is required" .Values.namespaceToken -}}
{{- $parts := splitList "-" $tok -}}
{{- if ne (len $parts) 2 -}}{{- fail (printf "namespaceToken %q must be <run>-<state>" $tok) -}}{{- end -}}
{{- $run := upper (trunc 7 (index $parts 0)) -}}
{{- $state := index $parts 1 -}}
{{- if eq $state "before" -}}{{ $run }}B{{- else if eq $state "after" -}}{{ $run }}A{{- else -}}{{- fail (printf "namespaceToken state %q must be before|after" $state) -}}{{- end -}}
{{- end -}}
{{- end -}}

{{/* Label values may not contain ':', so the label carries expires with '_' and the annotation the exact value. */}}
{{- define "db2-archive.labels" -}}
{{- if not (regexMatch "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$" .Values.expires) -}}{{- fail (printf "expires %q must be YYYY-MM-DDTHH:MM:SSZ" .Values.expires) -}}{{- end -}}
{{- if ne .Values.owner "otterworks-demo" -}}{{- fail "owner must be otterworks-demo" -}}{{- end -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
app.kubernetes.io/part-of: otterworks-ldm
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
demo/name: legacy-data-migration
demo/namespace: {{ .Values.namespaceToken | default .Release.Namespace | quote }}
demo/owner: {{ .Values.owner | quote }}
demo/expires: {{ .Values.expires | replace ":" "_" | quote }}
{{- end -}}

{{- define "db2-archive.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "db2-archive.annotations" -}}
demo/expires-at: {{ .Values.expires | quote }}
demo/owner: {{ .Values.owner | quote }}
{{- end -}}
