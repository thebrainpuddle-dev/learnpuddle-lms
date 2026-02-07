# ---------- Frontend Dockerfile ----------
# Stage 1: build the React app
FROM node:18-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --silent
COPY . .
ARG REACT_APP_API_URL=/api
ENV REACT_APP_API_URL=$REACT_APP_API_URL
RUN npm run build

# Stage 2: serve with nginx
FROM nginx:1.25-alpine
COPY --from=build /app/build /usr/share/nginx/html
# nginx config is volume-mounted from docker-compose (for wildcard subdomain support)
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
