# MemSOC gateway -- the React dashboard plus the unified API docs.
#
# This image is also the gateway: its nginx fronts both services on one
# origin so /api-docs can show every endpoint on a single page and call
# them for real. See deploy/nginx.conf.
#
# Build context is the REPO ROOT, so paths below are repo-relative.
#
# VITE_API_URL is baked in at BUILD time, because this bundle runs in the
# operator's browser, not in the Docker network: it must point at a
# host-reachable address (localhost:<published report port>), never at the
# internal `report` hostname. docker-compose.yml passes the same port it
# publishes for the report service, so the two cannot drift apart.

FROM node:22-alpine AS build

ARG VITE_API_URL=http://localhost:8001
ENV VITE_API_URL=${VITE_API_URL}

WORKDIR /app

COPY dashboard/package.json dashboard/package-lock.json ./
RUN npm ci

COPY dashboard/index.html dashboard/vite.config.js ./
COPY dashboard/src ./src
COPY dashboard/public ./public

RUN npm run build


FROM nginx:alpine

# Replaces the stock server block: static dashboard + /api-docs +
# proxies for /services/detection/ and /services/report/.
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf

# Includes public/api-docs/index.html, the Swagger UI page, which Vite
# copies verbatim from dashboard/public/.
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
