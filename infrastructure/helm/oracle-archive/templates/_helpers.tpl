{{/* Label values may not contain ':', so the label carries expires with '_' and the annotation the exact value. */}}
{{- define "oracle-archive.labels" -}}
{{- if not (regexMatch "^\\d{4}-\\d{2}-\\d{2}T\\d{2}:\\d{2}:\\d{2}Z$" .Values.expires) -}}{{- fail (printf "expires %q must be YYYY-MM-DDTHH:MM:SSZ" .Values.expires) -}}{{- end -}}
{{- if ne .Values.owner "otterworks-demo" -}}{{- fail "owner must be otterworks-demo" -}}{{- end -}}
{{- if not (regexMatch "^[a-z0-9]{1,8}-(before|after)$" (.Values.namespaceToken | default "")) -}}{{- fail (printf "namespaceToken %q must be <run>-<before|after>" .Values.namespaceToken) -}}{{- end -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Values.image.tag | quote }}
app.kubernetes.io/part-of: otterworks-ldm
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ printf "%s-%s" .Chart.Name .Chart.Version }}
demo/name: legacy-data-migration
demo/namespace: {{ .Values.namespaceToken | quote }}
demo/owner: {{ .Values.owner | quote }}
demo/expires: {{ .Values.expires | replace ":" "_" | quote }}
{{- end -}}

{{- define "oracle-archive.selectorLabels" -}}
app.kubernetes.io/name: {{ .Chart.Name }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{- define "oracle-archive.annotations" -}}
demo/expires-at: {{ .Values.expires | quote }}
demo/owner: {{ .Values.owner | quote }}
{{- end -}}

{{/* Digest-pinned image reference when image.digest is set, else repository:tag. */}}
{{- define "oracle-archive.image" -}}
{{- if .Values.image.digest -}}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag -}}
{{- end -}}
{{- end -}}

{{/* host:port/service DSN of this release's listener, as python-oracledb thin mode takes it. */}}
{{- define "oracle-archive.dsn" -}}
{{- printf "%s.%s.svc.cluster.local:%d/%s" .Release.Name .Release.Namespace (int .Values.database.port) .Values.database.service -}}
{{- end -}}
