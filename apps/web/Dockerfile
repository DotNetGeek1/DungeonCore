FROM node:20-alpine AS build

WORKDIR /app

COPY apps/web/package*.json ./
RUN npm install --no-audit --no-fund

COPY apps/web/index.html ./
COPY apps/web/tsconfig.json ./
COPY apps/web/vite.config.ts ./
COPY apps/web/src ./src
COPY apps/web/public ./public

RUN npm run build

FROM node:20-alpine AS runtime

WORKDIR /app

RUN npm install -g serve@14

COPY --from=build /app/dist /app/dist

EXPOSE 3000

CMD ["serve", "-s", "dist", "-l", "3000"]
