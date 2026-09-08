{{- define "otter-projects.name" -}}
otter-projects
{{- end -}}

{{- define "otter-projects.labels" -}}
app.kubernetes.io/name: {{ include "otter-projects.name" . }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/part-of: otterworks-demo-platform
platform/environment: {{ .Values.environment }}
platform/team: otterworks
{{- end -}}

{{- define "otter-projects.selectorLabels" -}}
app.kubernetes.io/name: {{ include "otter-projects.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/component: web
{{- end -}}

{{/*
Required 12-digit AWS account id — never hardcoded in tracked files. Forces
integer formatting so `--set` (float64) and `--set-string` both render the
literal digits. Prefer `--set-string awsAccountId=<id>`.
*/}}
{{- define "otter-projects.awsAccountId" -}}
{{- $id := required "awsAccountId is required (supply --set-string awsAccountId=<12-digit id>); it must NOT be committed" .Values.awsAccountId -}}
{{- if kindIs "float64" $id -}}
{{- printf "%.0f" $id -}}
{{- else -}}
{{- $id -}}
{{- end -}}
{{- end -}}

{{- define "otter-projects.roleName" -}}
{{- if .Values.serviceAccount.roleName -}}
{{- .Values.serviceAccount.roleName -}}
{{- else -}}
otterworks-otter-projects-{{ .Values.environment }}
{{- end -}}
{{- end -}}

{{- define "otter-projects.roleArn" -}}
arn:aws:iam::{{ include "otter-projects.awsAccountId" . }}:role/{{ include "otter-projects.roleName" . }}
{{- end -}}

{{- define "otter-projects.secretName" -}}
{{ .Release.Name }}
{{- end -}}
