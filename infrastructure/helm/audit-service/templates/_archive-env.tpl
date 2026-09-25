{{/*
Archive read-path env (migration/CONTRACTS.md §10.4). Rendered only when archive.store is
set, so tenants without ARCHIVE_STORE keep the golden behaviour (feature off, 404 + hint).
Credentials come from the Secret named by archive.credentialsSecret, never from values.
*/}}
{{- define "archive.env" }}
{{- with .Values.archive -}}
{{- if .store -}}
- name: ARCHIVE_STORE
  value: {{ .store | quote }}
{{- if .namespace }}
- name: LDM_NAMESPACE
  value: {{ .namespace | quote }}
{{- end }}
{{- if eq .store "db2" }}
- name: DB2_HOST
  value: {{ .db2.host | quote }}
- name: DB2_PORT
  value: {{ .db2.port | quote }}
- name: DB2_DATABASE
  value: {{ .db2.database | quote }}
- name: DB2_USER
  valueFrom:
    secretKeyRef:
      name: {{ .credentialsSecret }}
      key: DB2_USER
- name: DB2_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .credentialsSecret }}
      key: DB2_PASSWORD
{{- end }}
{{- if eq .store "azuresql" }}
- name: AZSQL_SERVER
  value: {{ .azuresql.server | quote }}
- name: AZSQL_DATABASE
  value: {{ .azuresql.database | quote }}
- name: AZSQL_AUTH
  value: {{ .azuresql.auth | quote }}
{{- if eq .azuresql.auth "sql" }}
- name: AZSQL_USER
  valueFrom:
    secretKeyRef:
      name: {{ .credentialsSecret }}
      key: AZSQL_USER
- name: AZSQL_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ .credentialsSecret }}
      key: AZSQL_PASSWORD
{{- else }}
- name: AZURE_CLIENT_ID
  valueFrom:
    secretKeyRef:
      name: {{ .credentialsSecret }}
      key: AZURE_CLIENT_ID
{{- end }}
{{- end }}
{{- end }}
{{- end }}
{{- end -}}
