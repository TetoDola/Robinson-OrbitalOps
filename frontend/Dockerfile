FROM node:22-alpine

WORKDIR /app

COPY frontend/package*.json ./
RUN npm ci

COPY frontend ./

ENV VITE_PROXY_API_TARGET=http://orbitops-backend:4000
ENV VITE_PROXY_WS_TARGET=ws://orbitops-backend:4000
EXPOSE 5173

CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
