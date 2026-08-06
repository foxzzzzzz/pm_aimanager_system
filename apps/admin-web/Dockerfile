FROM node:22-alpine

ARG NPM_REGISTRY=https://registry.npmjs.org

WORKDIR /app
RUN corepack enable
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml /app/
COPY apps/admin-web/package.json /app/apps/admin-web/package.json
COPY apps/mini-program/package.json /app/apps/mini-program/package.json
RUN pnpm config set registry "${NPM_REGISTRY}" \
    && pnpm install --frozen-lockfile
COPY apps/admin-web /app/apps/admin-web

EXPOSE 5173
CMD ["pnpm", "--filter", "@project-manager/admin-web", "dev"]
