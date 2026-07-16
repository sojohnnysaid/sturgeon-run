FROM node:22-slim

WORKDIR /app

# Install dependencies (including dev deps for the tsc build).
COPY package.json package-lock.json* ./
RUN npm ci

# Build.
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

ENV MCP_PORT=8081
EXPOSE 8081

CMD ["node", "dist/server.js"]
