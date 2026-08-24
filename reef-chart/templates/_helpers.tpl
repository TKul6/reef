{{/*
The chart name, overridable, capped at the 63 characters a Kubernetes name allows.
*/}}
{{- define "reef-server.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
The name every object is built from: the release, prefixed with the chart name unless the release
already carries it — so `helm install reef-server` yields reef-server, not reef-server-reef-server.
*/}}
{{- define "reef-server.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{- define "reef-server.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Labels for every object.

The version label reports image.tag rather than the chart's appVersion, because the application
being run is your image — appVersion only records which reef-server the chart was written against.
*/}}
{{- define "reef-server.labels" -}}
helm.sh/chart: {{ include "reef-server.chart" . }}
{{ include "reef-server.selectorLabels" . }}
app.kubernetes.io/version: {{ .Values.image.tag | default .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
The immutable subset of the labels. A Deployment's selector cannot be changed after creation, so
anything that moves between releases — chart version, image tag — must stay out of here.
*/}}
{{- define "reef-server.selectorLabels" -}}
app.kubernetes.io/name: {{ include "reef-server.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{- define "reef-server.serviceAccountName" -}}
{{- if .Values.serviceAccount.create }}
{{- default (include "reef-server.fullname" .) .Values.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.serviceAccount.name }}
{{- end }}
{{- end }}
