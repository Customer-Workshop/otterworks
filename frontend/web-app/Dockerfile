FROM node:20-alpine AS builder

ARG NEXT_PUBLIC_COLLAB_WS_URL=ws://localhost:8084
ARG API_GATEWAY_URL=http://api-gateway:8080
ENV NEXT_PUBLIC_COLLAB_WS_URL=$NEXT_PUBLIC_COLLAB_WS_URL
ENV API_GATEWAY_URL=$API_GATEWAY_URL

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM node:20-alpine
WORKDIR /app
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public

EXPOSE 3000
HEALTHCHECK --interval=10s --timeout=3s CMD wget --spider -q http://localhost:3000/ || exit 1
ENV NODE_ENV=production
# API_GATEWAY_URL default for runtime (can be overridden by Helm/docker-compose env)
ENV API_GATEWAY_URL=http://api-gateway:8080
CMD ["node", "server.js"]
