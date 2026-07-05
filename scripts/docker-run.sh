#!/usr/bin/env sh
set -eu

network_name="orbitops-net"
backend_name="orbitops-backend"
frontend_name="orbitops-frontend"
build_root="${TMPDIR:-/tmp}/orbitops-docker-build"

docker network inspect "$network_name" >/dev/null 2>&1 || docker network create "$network_name" >/dev/null

docker rm -f "$backend_name" >/dev/null 2>&1 || true
docker rm -f "$frontend_name" >/dev/null 2>&1 || true

rm -rf "$build_root"
mkdir -p "$build_root/backend-context" "$build_root/frontend-context"

cp package.json "$build_root/backend-context/"
cp -R backend "$build_root/backend-context/"
cp backend/Dockerfile "$build_root/backend-context/Dockerfile"

cp -R frontend "$build_root/frontend-context/"
cp frontend/Dockerfile "$build_root/frontend-context/Dockerfile"

docker build -t orbitops-backend "$build_root/backend-context"
docker build -t orbitops-frontend "$build_root/frontend-context"

docker run -d \
  --name "$backend_name" \
  --network "$network_name" \
  -p 4000:4000 \
  orbitops-backend >/dev/null

docker run -d \
  --name "$frontend_name" \
  --network "$network_name" \
  -p 3000:5173 \
  orbitops-frontend >/dev/null

printf "Frontend: http://localhost:3000\n"
printf "Backend health: http://localhost:4000/health\n"
