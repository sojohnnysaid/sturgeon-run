FROM node:22-slim

WORKDIR /app

# Install deps first for better layer caching.
COPY package.json package-lock.json* ./
RUN npm ci

COPY . .

EXPOSE 5173

# --host so the dev server is reachable from outside the container.
CMD ["npm", "run", "dev", "--", "--host"]
