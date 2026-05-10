# dockerlens

*A beautiful, self-hosted Docker dashboard for Linux servers.*

![license MIT](https://img.shields.io/badge/license-MIT-blue)
![python 3.12](https://img.shields.io/badge/python-3.12-blue)
![FastAPI 0.100+](https://img.shields.io/badge/FastAPI-0.100+-green)

## Screenshot

![dockerlens dashboard](docs/screenshot.png)

## Features

- One Docker container, one-line install
- Real-time dashboard with automatic refresh every 5 seconds
- Card per container with status, uptime, ports, CPU and RAM
- Real-time logs via WebSocket when clicking a card
- Direct actions: Start, Stop, Restart from the dashboard
- Two themes: Dawn (light) and Dark, with persistence in localStorage
- Automatic detection of the Docker socket GID
- Automatic free-port selection if 8080 is busy
- Compatible with any Linux distribution with Docker installed

## Requirements

On the target machine you only need:

- Docker (with the daemon running)
- Docker Compose (plugin or standalone)
- git

## Installation

```bash
curl -fsSL https://raw.githubusercontent.com/ihabfallahy2/dockerlens/main/install.sh | bash
```

The script automatically:

- Checks dependencies
- Clones the repository into `~/dockerlens`
- Detects the GID of the Docker socket
- Finds a free port if 8080 is occupied
- Builds the image and starts the container

When finished, the script prints the exact URL to open.

## Update

To update dockerlens, simply run the same install command again:

```bash
curl -fsSL https://raw.githubusercontent.com/ihabfallahy2/dockerlens/main/install.sh | bash
```

## Configuration

The installer creates a `.env` file with the following variables:

| Variable | Default | Description |
|---|---|---|
| `DOCKERLENS_PORT` | `8080` | Host port to expose the dashboard |
| `DOCKER_GID` | auto-detected | GID of the `docker` group on the host |
| `READ_ONLY` | `false` | Disable start/stop/restart actions |

To change the port before installing:

```bash
DOCKERLENS_PORT=9090 curl -fsSL https://raw.githubusercontent.com/ihabfallahy2/dockerlens/main/install.sh | bash
```

## Uninstall

```bash
cd ~/dockerlens
docker compose down --rmi all
cd ~
rm -rf ~/dockerlens
```

## Architecture

```
Browser → FastAPI (Python) → Docker SDK → /var/run/docker.sock
              ↑
         static/index.html (HTML + CSS + JS, no framework)
```

Everything runs in a single container that observes itself and its siblings.

## License

MIT
