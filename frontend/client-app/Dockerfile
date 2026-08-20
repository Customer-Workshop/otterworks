FROM node:20-alpine AS builder

ARG VITE_COLLAB_WS_URL=ws://localhost:8084
ENV VITE_COLLAB_WS_URL=$VITE_COLLAB_WS_URL

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx/default.conf.template /etc/nginx/templates/default.conf.template

EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s CMD wget -q -O /dev/null http://127.0.0.1:3000/ || exit 1

# API_GATEWAY_URL default for runtime (can be overridden by Helm/docker-compose env);
# substituted into the nginx config template at container start.
ENV API_GATEWAY_URL=http://api-gateway:8080

# Makes the base image publish the container's own nameservers as NGINX_LOCAL_RESOLVERS, which
# the config template uses to resolve the portal backends per request rather than at startup.
ENV NGINX_ENTRYPOINT_LOCAL_RESOLVERS=1

# Portal backend per bounded context. These now point at the extracted services; rolling a
# context back to the monolith is one env var (http://legacy-portal:8095) and a restart, with
# no rebuild. See docs/migration/traffic-routing.md.
ENV ANNOUNCEMENTS_API_URL=http://announcements-service:8101
ENV USER_PREFERENCES_API_URL=http://user-preferences-service:8102
ENV FEEDBACK_API_URL=http://feedback-service:8103
