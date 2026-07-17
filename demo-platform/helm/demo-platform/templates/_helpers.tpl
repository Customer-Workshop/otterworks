{{/* Common name / label helpers */}}

{{- define "demo-platform.name" -}}
demo-platform
{{- end -}}

{{- define "demo-platform.labels" -}}
app.kubernetes.io/name: {{ include "demo-platform.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: otterworks-demo-platform
platform/environment: {{ .Values.environment }}
platform/team: otterworks
{{- end -}}

{{- define "demo-platform.dashboardSelectorLabels" -}}
app.kubernetes.io/name: {{ include "demo-platform.name" . }}
app.kubernetes.io/component: ops-dashboard
{{- end -}}

{{/*
Required 12-digit AWS account id — never hardcoded in tracked files.
Rendered defensively: a bare `--set awsAccountId=<12-digit-id>` makes Helm parse
the value as a float (→ "5.99e+11" in the ARN, breaking IRSA). Force integer
formatting so both `--set` and `--set-string` produce the literal 12 digits.
Prefer `--set-string awsAccountId=<id>`.
*/}}
{{- define "demo-platform.awsAccountId" -}}
{{- $id := required "awsAccountId is required (supply --set-string awsAccountId=<12-digit id>); it must NOT be committed" .Values.awsAccountId -}}
{{- if kindIs "float64" $id -}}
{{- printf "%.0f" $id -}}
{{- else -}}
{{- $id -}}
{{- end -}}
{{- end -}}

{{/* IRSA role name (defaults to otterworks-demo-ops-dashboard-<environment>). */}}
{{- define "demo-platform.roleName" -}}
{{- if .Values.serviceAccount.roleName -}}
{{- .Values.serviceAccount.roleName -}}
{{- else -}}
otterworks-demo-ops-dashboard-{{ .Values.environment }}
{{- end -}}
{{- end -}}

{{/* Full IRSA role ARN for the dashboard/runner service account. */}}
{{- define "demo-platform.roleArn" -}}
arn:aws:iam::{{ include "demo-platform.awsAccountId" . }}:role/{{ include "demo-platform.roleName" . }}
{{- end -}}
