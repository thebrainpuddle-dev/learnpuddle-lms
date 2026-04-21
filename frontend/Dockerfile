# ---------- Frontend Dockerfile ----------
# Stage 1: build the React app
FROM node:18-alpine AS build
WORKDIR /app
# Limit Node memory (helps on 2GB Droplets; npm ci can OOM)
ENV NODE_OPTIONS=--max-old-space-size=1536
COPY package.json package-lock.json ./
RUN npm ci --legacy-peer-deps
COPY . .
# REACT_APP_* values come from .env.production via Vite's loadEnv.
# Do NOT declare them as ENV here — Vite's loadEnv treats an existing (empty)
# process.env entry as a user override and silently wins over the .env file.
ENV GENERATE_SOURCEMAP=false
RUN npm run build

# Stage 2: serve with nginx (non-root)
FROM nginx:1.25-alpine
COPY --from=build /app/build /usr/share/nginx/html

# Run nginx as non-root
RUN chown -R nginx:nginx /usr/share/nginx/html && \
    chown -R nginx:nginx /var/cache/nginx && \
    chown -R nginx:nginx /var/log/nginx && \
    touch /var/run/nginx.pid && \
    chown -R nginx:nginx /var/run/nginx.pid
USER nginx

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=3s --retries=3 \
    CMD wget -qO- http://localhost:80/ || exit 1

CMD ["nginx", "-g", "daemon off;"]
