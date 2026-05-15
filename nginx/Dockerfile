# nginx/Dockerfile — Builds frontend into nginx image (no volume copy)
# Context: project root (docker-compose uses context: .)
#
# This eliminates the frontend_build volume and copy step, which was
# causing 404s when the volume had stale/wrong content.

# Stage 1: Build React app
FROM node:20-alpine AS frontend-build
WORKDIR /app
ARG BUILD_SHA=nogit
ENV NODE_OPTIONS=--max-old-space-size=1536 \
    BUILD_SHA=${BUILD_SHA}
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY frontend/ .
# REACT_APP_* values come from frontend/.env.production via Vite's loadEnv.
# Do NOT declare them as ENV here — Vite's loadEnv treats an existing (empty)
# process.env entry as a user override and silently wins over the .env file.
ENV GENERATE_SOURCEMAP=false \
    CI=false
RUN npm run build

# Stage 2: Nginx with frontend baked in
FROM nginx:1.25-alpine
COPY --from=frontend-build /app/build /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
# Bake in supporting config files so the image is self-contained.
# Production/staging override default.conf at runtime via volume mount, but
# having these files in the image means the container can also start cleanly
# without any volume mounts (e.g. smoke tests, standalone runs).
COPY nginx/includes/ /etc/nginx/includes/
COPY nginx/proxy_params /etc/nginx/proxy_params
# Fix ownership so nginx user can write to cache, logs, and pid file.
# NET_BIND_SERVICE capability (granted by Docker by default) allows
# the non-root nginx process to bind to privileged ports 80 and 443.
RUN chown -R nginx:nginx /var/cache/nginx \
    && chown -R nginx:nginx /var/log/nginx \
    && chown -R nginx:nginx /etc/nginx/conf.d \
    && touch /var/run/nginx.pid \
    && chown nginx:nginx /var/run/nginx.pid
# static_data and media_data are mounted at runtime
USER nginx
EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
