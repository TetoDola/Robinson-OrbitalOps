FROM node:22-alpine

WORKDIR /app

COPY package.json ./
COPY backend ./backend

ENV PORT=4000
EXPOSE 4000

CMD ["node", "backend/server.mjs"]
