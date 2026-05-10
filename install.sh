#!/usr/bin/env bash
set -euo pipefail

trap 'echo ""; echo "✖ El instalador falló en la línea $LINENO. Revisa los mensajes anteriores."; exit 1' ERR

# ── Colores ─────────────────────────────────────────────────────────
if command -v tput &>/dev/null; then
    GREEN=$(tput setaf 2)
    YELLOW=$(tput setaf 3)
    RED=$(tput setaf 1)
    RESET=$(tput sgr0)
else
    GREEN='\033[0;32m'
    YELLOW='\033[0;33m'
    RED='\033[0;31m'
    RESET='\033[0m'
fi

# ── Variables configurables ─────────────────────────────────────────
REPO_URL="https://github.com/ihabfallahy2/dockerlens.git"
INSTALL_DIR="${HOME}/dockerlens"
PORT="${DOCKERLENS_PORT:-8080}"

# ── Comprobaciones previas ──────────────────────────────────────────

if ! command -v docker &>/dev/null; then
    echo "${RED}✖ Docker no está instalado.${RESET}"
    echo "  Instálalo desde: https://docs.docker.com/engine/install/"
    exit 1
fi

if ! docker info &>/dev/null; then
    echo "${RED}✖ El daemon de Docker no está corriendo.${RESET}"
    echo "  Prueba: sudo systemctl start docker"
    exit 1
fi

if docker compose version &>/dev/null 2>&1; then
    COMPOSE_CMD="docker compose"
elif command -v docker-compose &>/dev/null; then
    COMPOSE_CMD="docker-compose"
else
    echo "${RED}✖ Docker Compose no está instalado.${RESET}"
    echo "  Instálalo desde: https://docs.docker.com/compose/install/"
    exit 1
fi

if ! command -v git &>/dev/null; then
    echo "${RED}✖ git no está instalado.${RESET}"
    echo "  Instálalo con: sudo apt install git  (o el gestor de tu distro)"
    exit 1
fi

# ── Detección del puerto ────────────────────────────────────────────
find_free_port() {
    local port=$1
    while ss -tlnp 2>/dev/null | grep -q ":${port} " || \
          netstat -tlnp 2>/dev/null | grep -q ":${port} "; do
        port=$((port + 1))
    done
    echo "$port"
}
PORT=$(find_free_port "$PORT")

# ── Clonar o actualizar ─────────────────────────────────────────────
if [ -d "$INSTALL_DIR/.git" ]; then
    echo "▸ Actualizando repositorio existente..."
    git -C "$INSTALL_DIR" pull --ff-only
else
    echo "▸ Clonando dockerlens en $INSTALL_DIR..."
    git clone "$REPO_URL" "$INSTALL_DIR"
fi
cd "$INSTALL_DIR"

# ── Configuración ───────────────────────────────────────────────────
DOCKER_GID=$(stat -c '%g' /var/run/docker.sock 2>/dev/null || echo "999")

cat > .env <<EOF
DOCKER_GID=${DOCKER_GID}
DOCKERLENS_PORT=${PORT}
READ_ONLY=false
EOF

echo "${GREEN}✔ Configuración: puerto ${PORT}, Docker GID ${DOCKER_GID}${RESET}"

# ── Construir y arrancar ────────────────────────────────────────────
echo "▸ Construyendo imagen (puede tardar un momento la primera vez)..."
$COMPOSE_CMD up -d --build

echo ""
echo "${GREEN}✔ dockerlens instalado correctamente.${RESET}"
echo ""
echo "  Abre en tu navegador:"

LOCAL_IP=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo "  → http://localhost:${PORT}"
echo "  → http://${LOCAL_IP}:${PORT}  (desde otros dispositivos en tu red)"
echo ""
echo "  Para pararlo:     cd ${INSTALL_DIR} && ${COMPOSE_CMD} down"
echo "  Para actualizarlo: curl -fsSL https://raw.githubusercontent.com/ihabfallahy2/dockerlens/main/install.sh | bash"
