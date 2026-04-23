FROM node:20-alpine AS builder

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:1.25-alpine
COPY --from=builder /app/dist/admin-dashboard/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

RUN adduser -D -u 1001 appuser
USER appuser

EXPOSE 4200
HEALTHCHECK --interval=10s --timeout=3s CMD wget --spider -q http://localhost:4200/ || exit 1
