FROM node:22-alpine AS build
WORKDIR /app/services/web
COPY services/web/package.json services/web/package-lock.json* ./
RUN npm ci
COPY services/web .
COPY shared/visitor-industries.json /app/shared/visitor-industries.json
RUN npm run build

FROM nginx:1.27-alpine
COPY services/web/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/services/web/dist /usr/share/nginx/html
EXPOSE 80
