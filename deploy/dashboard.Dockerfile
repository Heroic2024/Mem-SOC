# MemSOC gateway -- the React dashboard plus the unified API docs.
#
# This image is also the gateway: its nginx fronts both services on one
# origin so /api-docs can show every endpoint on a single page and call
# them for real. See deploy/nginx.conf.
#
# Build context is the REPO ROOT, so paths below are repo-relative.
#
# The bundle fetches the report API at a RELATIVE path
# (/services/report/...), which this container's own nginx proxies. So
# there is no API URL to bake in at build time: the browser calls
# whatever host it loaded the page from, and the image is identical
# whatever port the report service is published on.

FROM node:22-alpine AS build

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
