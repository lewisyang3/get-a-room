# Development image: runs the Vite dev server. Compose bind-mounts the source
# over /app, so edits on the host reload in the browser.
FROM node:22-alpine

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

EXPOSE 3000

CMD ["npm", "run", "dev"]
