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

{{/* Required 12-digit AWS account id — never hardcoded in tracked files. */}}
{{- define "demo-platform.awsAccountId" -}}
{{- required "awsAccountId is required (supply --set awsAccountId=<12-digit id>); it must NOT be committed" .Values.awsAccountId -}}
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
