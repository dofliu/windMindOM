"""
windMindOM Wind Farm Monitor Platform - Entry Point.

Usage:
    python run.py                # Start backend (port from .env, default 8100)
    python run.py --port 9000    # Override port

WMOM-20260503-01：M1 repo baseline 整理後，monitoring 子系統（simulator、
server、wind_model、scada_system 等）已搬到 ``modules/monitoring/``。
為避免大規模改動既有 ``from simulator.x`` / ``from server.x`` 的 import，
本檔案把 ``modules/monitoring/`` 注入 sys.path 最前面，讓 legacy import
在新位置依然可解析。長期重構（另開 issue）會改為明確 import。
"""

import sys
import os
import argparse
import socket

_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
_MONITORING_ROOT = os.path.join(_PROJECT_ROOT, "modules", "monitoring")

# 順序：monitoring 在最前面（解析 ``from simulator.x`` 等 legacy import），
# 其次 project root（解析 ``from modules.x`` 與 ``from shared.x``）。
sys.path.insert(0, _PROJECT_ROOT)
sys.path.insert(0, _MONITORING_ROOT)


def _load_dotenv():
    """Load .env file from project root into os.environ (no dependency needed)."""
    env_path = os.path.join(_PROJECT_ROOT, ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


def _port_available(port: int, host: str = "0.0.0.0") -> bool:
    """Check if a TCP port is available."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind((host, port))
            return True
    except OSError:
        return False


def _find_available_port(start: int, host: str = "0.0.0.0", max_tries: int = 10) -> int:
    """Find an available port starting from `start`, incrementing by 1."""
    for offset in range(max_tries):
        port = start + offset
        if _port_available(port, host):
            return port
    return start  # fallback


def main():
    """Parse CLI arguments and start the backend server with uvicorn."""
    _load_dotenv()

    default_port = int(os.environ.get("BACKEND_PORT", "8100"))
    default_host = os.environ.get("BACKEND_HOST", "0.0.0.0")
    modbus_port = int(os.environ.get("MODBUS_PORT", "5020"))

    parser = argparse.ArgumentParser(description="Wind Farm Monitor Platform")
    parser.add_argument("--port", type=int, default=default_port,
                        help=f"Server port (default: {default_port})")
    parser.add_argument("--host", type=str, default=default_host,
                        help=f"Server host (default: {default_host})")
    parser.add_argument("--reload", action="store_true",
                        help="Enable auto-reload for development")
    parser.add_argument("--auto-port", action="store_true",
                        help="Auto-find available port if default is busy")
    args = parser.parse_args()

    port = args.port
    if not _port_available(port, args.host):
        if args.auto_port:
            old_port = port
            port = _find_available_port(port + 1, args.host)
            print(f"[run] Port {old_port} is busy, using {port} instead")
        else:
            print(f"[run] WARNING: Port {port} appears to be in use.")
            print("[run]   Use --auto-port to auto-select, or --port <N> to specify another.")

    # Export actual port so other code can reference it
    os.environ["BACKEND_PORT"] = str(port)

    print(f"[run] Starting backend on {args.host}:{port}")
    print(f"[run] Modbus TCP on port {modbus_port}")
    print(f"[run] Frontend should connect to http://localhost:{port}")

    import uvicorn
    uvicorn.run(
        "server.app:app",
        host=args.host,
        port=port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
