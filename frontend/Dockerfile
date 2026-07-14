FROM node:20-bookworm-slim AS build

WORKDIR /frontend

ENV HTTP_PROXY=
ENV HTTPS_PROXY=
ENV ALL_PROXY=
ENV http_proxy=
ENV https_proxy=
ENV all_proxy=

COPY package.json package-lock.json ./
RUN npm install -g pnpm@9.15.4 --no-fund --no-audit \
    && pnpm install --no-frozen-lockfile

COPY . .
RUN pnpm run build

FROM nginx:1.27-alpine

COPY --from=build /frontend/dist /usr/share/nginx/html

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
