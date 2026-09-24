FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.25-alpine
COPY --from=builder /app/dist/admin-dashboard/browser /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
# The image's entrypoint renders /etc/nginx/templates/*.template with envsubst; restrict
# substitution to PEER_APP_URL so nginx variables ($uri, $http_host, ...) survive.
ENV NGINX_ENVSUBST_FILTER=^PEER_APP_URL$ \
    PEER_APP_URL=""

EXPOSE 4200
HEALTHCHECK --interval=10s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1:4200/ || exit 1
