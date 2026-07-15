FROM node:20-bookworm-slim AS build

WORKDIR /frontend

ARG HTTP_PROXY
ARG HTTPS_PROXY
ARG ALL_PROXY
ARG http_proxy
ARG https_proxy
ARG all_proxy

ENV HTTP_PROXY=${HTTP_PROXY}
ENV HTTPS_PROXY=${HTTPS_PROXY}
ENV ALL_PROXY=${ALL_PROXY}
ENV http_proxy=${http_proxy}
ENV https_proxy=${https_proxy}
ENV all_proxy=${all_proxy}

COPY package.json package-lock.json ./
RUN npm install -g pnpm@9.15.4 --no-fund --no-audit \
    && pnpm install --no-frozen-lockfile

COPY . .
RUN pnpm run build

FROM nginx:1.27-alpine

COPY --from=build /frontend/dist /usr/share/nginx/html

EXPOSE 8080

CMD ["nginx", "-g", "daemon off;"]
