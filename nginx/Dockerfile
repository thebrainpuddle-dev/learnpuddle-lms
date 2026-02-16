# nginx/Dockerfile — Builds frontend into nginx image (no volume copy)
# Context: project root (docker-compose uses context: .)
#
# This eliminates the frontend_build volume and copy step, which was
# causing 404s when the volume had stale/wrong content.

# Stage 1: Build React app
FROM node:18-alpine AS frontend-build
WORKDIR /app
ENV NODE_OPTIONS=--max-old-space-size=1536
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY frontend/ .
ARG REACT_APP_API_URL=/api
ENV REACT_APP_API_URL=$REACT_APP_API_URL \
    GENERATE_SOURCEMAP=false
RUN npm run build

# Stage 2: Nginx with frontend baked in
FROM nginx:1.25-alpine
COPY --from=frontend-build /app/build /usr/share/nginx/html
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
# static_data and media_data are mounted at runtime
EXPOSE 80 443
CMD ["nginx", "-g", "daemon off;"]
