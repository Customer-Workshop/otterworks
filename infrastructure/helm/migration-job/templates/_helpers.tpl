{{- define "migration-job.token" -}}
{{- required "namespaceToken is required (e.g. d24-after)" .Values.namespaceToken -}}
{{- end -}}

{{/* image.repository, defaulting to the per-token ECR repository <registry>/<prefix>/<token>/ldm-job */}}
{{- define "migration-job.image" -}}
{{- $repo := .Values.image.repository | default (printf "%s/%s/%s/ldm-job" .Values.image.registry .Values.image.repositoryPrefix (include "migration-job.token" .)) -}}
{{- printf "%s:%s" $repo (required "image.tag must be set (ECR uses IMMUTABLE tags)" .Values.image.tag) -}}
{{- end -}}

{{- define "migration-job.runId" -}}
{{- if eq .Values.stage "init" -}}init{{- else -}}
{{- required "runId is required for every stage except init" .Values.runId -}}
{{- end -}}
{{- end -}}

{{/* ldm-<stage>-<run_id>, truncated to the 63-char DNS label limit */}}
{{- define "migration-job.name" -}}
{{- if eq .Values.stage "init" -}}
{{- printf "ldm-init-%s" (include "migration-job.token" .) | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "ldm-%s-%s" .Values.stage .Values.runId | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "migration-job.labels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: {{ .Values.stage }}
app.kubernetes.io/part-of: otterworks-ldm
app.kubernetes.io/managed-by: {{ .Release.Service }}
platform/environment: {{ (.Values.global).environment | default "dev" }}
platform/team: otterworks
demo/namespace: {{ include "migration-job.token" . }}
demo/name: legacy-data-migration
demo/owner: otterworks-demo
demo/expires: {{ required "expires is required (YYYY-MM-DDTHH:MM:SSZ)" .Values.expires | replace ":" "_" | quote }}
{{- end -}}

{{- define "migration-job.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
