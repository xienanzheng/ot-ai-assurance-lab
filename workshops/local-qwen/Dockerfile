FROM node:22-alpine AS web
WORKDIR /web
COPY web/package*.json ./
RUN npm ci
COPY web/ ./
RUN npm run build
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml ./
RUN python -c "import tomllib,subprocess; subprocess.check_call(['pip','install','--no-cache-dir',*tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']])"
COPY v2/ ./v2/
COPY process_packages/ ./process_packages/
COPY --from=web /web/dist ./web/dist
RUN useradd --uid 10001 --create-home bench
USER bench
CMD ["uvicorn", "v2.api:factory", "--factory", "--host", "0.0.0.0", "--port", "8090"]
