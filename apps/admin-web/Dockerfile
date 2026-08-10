FROM node:22-alpine AS build

ARG NPM_REGISTRY=https://registry.npmjs.org
ARG VITE_API_BASE_URL=http://localhost:18000/api/v1
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml /app/
COPY apps/admin-web/package.json /app/apps/admin-web/package.json
COPY apps/mini-program/package.json /app/apps/mini-program/package.json
RUN pnpm config set registry "${NPM_REGISTRY}" \
    && pnpm install --frozen-lockfile
COPY apps/admin-web /app/apps/admin-web
RUN pnpm --filter @project-manager/admin-web build

FROM nginx:1.27-alpine
COPY --from=build /app/apps/admin-web/dist /usr/share/nginx/html

EXPOSE 80
