#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$APP_DIR"

need_cmd() {
  command -v "$1" >/dev/null 2>&1
}

if ! need_cmd docker; then
  echo "Docker is not installed. Installing Docker with get.docker.com..."
  curl -fsSL https://get.docker.com | sh
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "Docker Compose plugin is required. Please install Docker Compose v2 first."
  exit 1
fi

mkdir -p data

if [ ! -f config.json ]; then
  cp config.example.json config.json
fi

detect_image() {
  if [ -n "${CHATGPT2API_IMAGE:-}" ]; then
    printf '%s\n' "$CHATGPT2API_IMAGE"
    return
  fi

  remote="$(git remote get-url origin 2>/dev/null || true)"
  remote="${remote%.git}"

  case "$remote" in
    https://github.com/*)
      repo="${remote#https://github.com/}"
      ;;
    git@github.com:*)
      repo="${remote#git@github.com:}"
      ;;
    *)
      repo="YOUR_NAME/YOUR_REPO"
      ;;
  esac

  printf 'ghcr.io/%s/chatgpt2api:latest\n' "$(printf '%s' "$repo" | cut -d/ -f1 | tr '[:upper:]' '[:lower:]')"
}

if [ ! -f .env ]; then
  AUTH_KEY="${CHATGPT2API_AUTH_KEY:-$(openssl rand -hex 16)}"
  IMAGE="$(detect_image)"
  cat > .env <<EOF
CHATGPT2API_IMAGE=$IMAGE
CHATGPT2API_PORT=3000
CHATGPT2API_AUTH_KEY=$AUTH_KEY
CHATGPT2API_BASE_URL=
STORAGE_BACKEND=json
DATABASE_URL=
EOF
  echo "Generated .env with auth key: $AUTH_KEY"
elif ! grep -q '^CHATGPT2API_IMAGE=' .env; then
  echo "CHATGPT2API_IMAGE=$(detect_image)" >> .env
fi

if grep -q '"auth-key": "CHANGE_ME"' config.json; then
  AUTH_KEY="$(grep '^CHATGPT2API_AUTH_KEY=' .env | cut -d= -f2-)"
  sed -i "s/\"auth-key\": \"CHANGE_ME\"/\"auth-key\": \"$AUTH_KEY\"/" config.json
fi

if ! docker compose pull; then
  echo "Could not pull CHATGPT2API_IMAGE. Falling back to local Docker build."
  docker compose -f docker-compose.local.yml up -d --build
else
  docker compose up -d
fi

PORT="$(grep '^CHATGPT2API_PORT=' .env | cut -d= -f2- || true)"
PORT="${PORT:-3000}"

echo
echo "chatgpt2api is running."
echo "Web: http://YOUR_SERVER_IP:$PORT"
echo "Auth key: $(grep '^CHATGPT2API_AUTH_KEY=' .env | cut -d= -f2-)"
echo
echo "Useful commands:"
echo "  docker compose logs -f"
echo "  docker compose restart"
echo "  bash scripts/update-linux.sh"
