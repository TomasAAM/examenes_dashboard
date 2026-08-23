"""Web server entry point."""

from __future__ import annotations

import argparse

import uvicorn


def main() -> None:
    """Run the Exámenes web server."""
    parser = argparse.ArgumentParser(description="Run the Exámenes web server.")
    parser.add_argument("--host", default="0.0.0.0", help="Host interface (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on (default: 8000)")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload for development")

    args = parser.parse_args()

    print("\n=======================================================")
    print(f"[*] Examenes Lab Visualizer running at http://localhost:{args.port}")
    print(f"[*] Access from phone on Wi-Fi: http://<your-lan-ip>:{args.port}")
    print("=======================================================\n")

    uvicorn.run(
        "examenes.web.api:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
