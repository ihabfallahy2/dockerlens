import asyncio
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import docker
from docker.errors import APIError, NotFound
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles


READ_ONLY = os.getenv("READ_ONLY", "false").lower() == "true"

app = FastAPI(title="dockerlens")
client = docker.from_env()


def parse_docker_dt(value: str | None) -> datetime | None:
    if not value or value.startswith("0001-"):
        return None
    clean = value.replace("Z", "+00:00")
    if "." in clean:
        head, tail = clean.split(".", 1)
        zone = "+00:00" if "+" in tail else ""
        frac = tail.split("+", 1)[0][:6].ljust(6, "0")
        clean = f"{head}.{frac}{zone}"
    try:
        return datetime.fromisoformat(clean)
    except ValueError:
        return None


def uptime_from(started_at: str | None, running: bool) -> str:
    if not running:
        return "—"
    started = parse_docker_dt(started_at)
    if not started:
        return "—"
    delta = datetime.now(timezone.utc) - started
    minutes = max(int(delta.total_seconds() // 60), 0)
    days, rem = divmod(minutes, 1440)
    hours, mins = divmod(rem, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {mins}m"
    return f"{mins}m"


def image_name(container, attrs: dict) -> str:
    tags = getattr(container.image, "tags", None) or attrs.get("RepoTags") or attrs.get("ImageTags") or []
    if tags:
        return tags[0]
    config = attrs.get("Config") or {}
    return config.get("Image") or "—"


def status_from(attrs: dict) -> str:
    state = attrs.get("State") or {}
    if state.get("Running"):
        return "running"
    if int(state.get("ExitCode") or 0) != 0:
        return "error"
    return "stopped"


def format_ports(attrs: dict) -> str:
    ports = ((attrs.get("NetworkSettings") or {}).get("Ports")) or {}
    mapped = []
    for container_port, bindings in ports.items():
        port_num = container_port.split("/", 1)[0]
        if bindings:
            for binding in bindings:
                host_port = binding.get("HostPort")
                if host_port:
                    mapped.append(f"{host_port}:{port_num}")
        else:
            mapped.append(port_num)
        if len(mapped) >= 3:
            break
    return ", ".join(mapped[:3]) if mapped else "—"


def networks(attrs: dict) -> str:
    nets = ((attrs.get("NetworkSettings") or {}).get("Networks")) or {}
    return ", ".join(nets.keys()) if nets else "—"


def restart_policy(attrs: dict) -> str:
    policy = ((attrs.get("HostConfig") or {}).get("RestartPolicy")) or {}
    return policy.get("Name") or "no"


def calculate_stats(container) -> dict:
    raw = container.stats(stream=False)
    cpu_stats = raw.get("cpu_stats") or {}
    pre_cpu = raw.get("precpu_stats") or {}
    cpu_total = ((cpu_stats.get("cpu_usage") or {}).get("total_usage")) or 0
    pre_total = ((pre_cpu.get("cpu_usage") or {}).get("total_usage")) or 0
    system_total = cpu_stats.get("system_cpu_usage") or 0
    pre_system = pre_cpu.get("system_cpu_usage") or 0
    cpu_delta = cpu_total - pre_total
    system_delta = system_total - pre_system
    online = cpu_stats.get("online_cpus")
    if not online:
        online = len(((cpu_stats.get("cpu_usage") or {}).get("percpu_usage")) or []) or 1
    cpu = 0.0
    if cpu_delta > 0 and system_delta > 0:
        cpu = (cpu_delta / system_delta) * online * 100.0

    memory = raw.get("memory_stats") or {}
    usage = memory.get("usage") or 0
    limit = memory.get("limit") or 0
    stats = memory.get("stats") or {}
    cache = stats.get("cache") or stats.get("inactive_file") or 0
    ram = 0.0
    if limit > 0:
        ram = max(usage - cache, 0) / limit * 100.0

    networks_raw = raw.get("networks") or {}
    net_in = sum((net.get("rx_bytes") or 0) for net in networks_raw.values())
    net_out = sum((net.get("tx_bytes") or 0) for net in networks_raw.values())
    return {
        "cpu": round(cpu, 1),
        "ram": round(ram, 1),
        "netIn": net_in,
        "netOut": net_out,
    }


def container_payload(container) -> dict:
    container.reload()
    attrs = container.attrs
    state = attrs.get("State") or {}
    status = status_from(attrs)
    payload = {
        "id": container.id[:12],
        "name": attrs.get("Name", container.name).lstrip("/") or container.name,
        "image": image_name(container, attrs),
        "imageFull": (attrs.get("Config") or {}).get("Image") or image_name(container, attrs),
        "status": status,
        "uptime": uptime_from(state.get("StartedAt"), status == "running"),
        "ports": format_ports(attrs),
        "restart": restart_policy(attrs),
        "network": networks(attrs),
        "created": (parse_docker_dt(attrs.get("Created")) or datetime.now(timezone.utc)).date().isoformat(),
    }
    if status == "running":
        try:
            payload.update(calculate_stats(container))
        except APIError:
            payload.update({"cpu": 0.0, "ram": 0.0, "netIn": 0, "netOut": 0})
    return payload


def get_container(cid: str):
    try:
        return client.containers.get(cid)
    except NotFound as exc:
        raise HTTPException(404, "Contenedor no encontrado") from exc
    except APIError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/containers")
def list_containers():
    try:
        containers = client.containers.list(all=True)
        with ThreadPoolExecutor(max_workers=16) as executor:
            return list(executor.map(container_payload, containers))
    except APIError as exc:
        raise HTTPException(500, str(exc)) from exc


@app.get("/api/containers/{cid}")
def container_detail(cid: str):
    return container_payload(get_container(cid))


@app.post("/api/containers/{cid}/{action}")
def container_action(cid: str, action: str):
    if READ_ONLY:
        raise HTTPException(403, "Modo solo lectura activo")
    if action not in {"start", "stop", "restart"}:
        raise HTTPException(400, "Acción inválida")
    container = get_container(cid)
    try:
        getattr(container, action)()
    except APIError as exc:
        raise HTTPException(500, str(exc)) from exc
    return {"ok": True}


@app.websocket("/ws/logs/{cid}")
async def logs_ws(websocket: WebSocket, cid: str):
    await websocket.accept()
    try:
        container = client.containers.get(cid)
    except NotFound:
        await websocket.close(code=1008)
        return
    except APIError:
        await websocket.close(code=1011)
        return

    log_iter = None
    stop_logs = threading.Event()
    queue: asyncio.Queue[str | None] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def queue_line(line: str | None):
        try:
            asyncio.run_coroutine_threadsafe(queue.put(line), loop)
        except RuntimeError:
            pass

    def read_logs():
        try:
            for raw_line in log_iter:
                if stop_logs.is_set():
                    break
                line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
                queue_line(line)
        except Exception:
            pass
        finally:
            queue_line(None)

    try:
        log_iter = container.logs(stream=True, follow=True, tail=80, timestamps=True)
        threading.Thread(target=read_logs, daemon=True).start()
        while True:
            log_task = asyncio.create_task(queue.get())
            client_task = asyncio.create_task(websocket.receive_text())
            done, pending = await asyncio.wait(
                {log_task, client_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if client_task in done:
                client_task.result()
                continue
            line = log_task.result()
            if line is None:
                break
            await websocket.send_text(line)
    except WebSocketDisconnect:
        pass
    except RuntimeError:
        pass
    except APIError:
        try:
            await websocket.close(code=1011)
        except RuntimeError:
            pass
    finally:
        stop_logs.set()
        if log_iter and hasattr(log_iter, "close"):
            log_iter.close()


app.mount("/", StaticFiles(directory="static", html=True), name="static")
