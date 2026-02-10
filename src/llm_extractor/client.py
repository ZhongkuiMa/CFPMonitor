"""Ollama client with SSH tunnel management and retry logic."""

import atexit
import json
import socket
import subprocess
import time

from json_repair import repair_json
from ollama import Client, ResponseError

_tunnel_proc: subprocess.Popen | None = None


def _is_port_open(host: str, port: int) -> bool:
    """Check whether a TCP port accepts connections."""
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def _ensure_tunnel(config: dict) -> None:
    """Start an SSH tunnel if configured and not already running.

    :param config: Full config dict from config.yaml.
    :raises ConnectionError: If the tunnel fails to start.
    """
    global _tunnel_proc

    cfg = config.get("ssh_tunnel", {})
    if not cfg.get("enabled", False):
        return

    local_port = cfg.get("local_port", 11434)
    if _is_port_open("localhost", local_port):
        return
    if _tunnel_proc is not None and _tunnel_proc.poll() is None:
        return

    host = cfg["host"]
    port = cfg.get("port", 22)
    user = cfg["username"]
    remote_host = cfg.get("remote_host", "localhost")
    remote_port = cfg.get("remote_port", 11434)

    print(f"  [+] Opening SSH tunnel to {user}@{host}:{port} ...")
    _tunnel_proc = subprocess.Popen(
        [
            "ssh",
            "-N",
            "-L",
            f"{local_port}:{remote_host}:{remote_port}",
            "-p",
            str(port),
            "-o",
            "StrictHostKeyChecking=no",
            "-o",
            "ServerAliveInterval=30",
            "-o",
            "ServerAliveCountMax=3",
            f"{user}@{host}",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    for _ in range(20):
        if _is_port_open("localhost", local_port):
            break
        if _tunnel_proc.poll() is not None:
            stderr = _tunnel_proc.stderr.read().decode().strip()
            raise ConnectionError(f"SSH tunnel failed: {stderr}")
        time.sleep(0.5)
    else:
        raise ConnectionError("SSH tunnel: port not reachable after 10s")

    print(
        f"  [+] SSH tunnel active: localhost:{local_port} -> {remote_host}:{remote_port}"
    )
    atexit.register(_close_tunnel)


def _close_tunnel() -> None:
    """Terminate the SSH tunnel subprocess."""
    global _tunnel_proc
    if _tunnel_proc is not None and _tunnel_proc.poll() is None:
        _tunnel_proc.terminate()
        _tunnel_proc.wait(timeout=5)
        _tunnel_proc = None


class OllamaClient:
    """Ollama API client with tunnel, model loading, and retry support."""

    def __init__(self, config: dict) -> None:
        """
        :param config: Full config dict from config.yaml.
        """
        self._config = config
        ollama = config["ollama"]
        self._host = ollama["host"]
        self._model = ollama["model"]
        self._options = ollama.get("options", {})
        self._keep_alive = ollama.get("keep_alive", "30m")
        self._retry_count = config["extraction"].get("retry_count", 2)
        self._retry_delay = config["extraction"].get("retry_delay_seconds", 5)
        self._client: Client | None = None

    def _get_client(self) -> Client:
        """Return the Ollama client, starting the tunnel first if needed."""
        if self._client is None:
            _ensure_tunnel(self._config)
            self._client = Client(host=self._host)
        return self._client

    def _is_model_loaded(self) -> bool:
        """Check whether the configured model is already in GPU/RAM."""
        response = self._get_client().ps()
        return any(
            m.model == self._model or m.model.startswith(f"{self._model}:")
            for m in response.models
        )

    def _load_model(self) -> None:
        """Load the configured model into memory if not already loaded."""
        if self._is_model_loaded():
            print(f"  [+] Model '{self._model}' already loaded in memory")
            return

        print(
            f"  [+] Loading model '{self._model}' (keep_alive={self._keep_alive}) ..."
        )
        t0 = time.time()
        self._get_client().generate(
            model=self._model,
            prompt="",
            keep_alive=self._keep_alive,
        )
        print(f"  [+] Model loaded in {time.time() - t0:.1f}s")

    def health_check(self) -> bool:
        """Verify server connectivity, model availability, and load model.

        :returns: True if the server and model are ready.
        """
        try:
            available = [m.model for m in self._get_client().list().models]
        except (ConnectionError, OSError) as e:
            print(f"  [!] Cannot connect to Ollama: {e}")
            return False

        model_found = any(
            m == self._model or m.startswith(f"{self._model}:") for m in available
        )
        if not model_found:
            print(
                f"  [!] Model '{self._model}' not found. Available: {', '.join(available)}"
            )
            return False

        print(f"  [+] Ollama OK: {len(available)} model(s) on server")
        self._load_model()
        return True

    def extract(self, system_prompt: str, user_prompt: str) -> dict | None:
        """Send a chat request and return parsed JSON.

        Retries on JSON parse errors and Ollama errors.

        :param system_prompt: System message.
        :param user_prompt: User message with data.
        :returns: Parsed JSON dict, or None if all attempts fail.
        """
        client = self._get_client()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        for attempt in range(1 + self._retry_count):
            try:
                response = client.chat(
                    model=self._model,
                    messages=messages,
                    format="json",
                    options=self._options,
                    keep_alive=self._keep_alive,
                )
                result = json.loads(response.message.content)
                if isinstance(result, dict):
                    return result
                print(f"  [!] LLM returned {type(result).__name__}, expected dict")
            except json.JSONDecodeError as e:
                print(f"  [!] JSON parse error (attempt {attempt + 1}): {e}")
                repaired = repair_json(response.message.content, return_objects=True)
                if isinstance(repaired, dict):
                    print("  [+] JSON repaired successfully")
                    return repaired
            except ResponseError as e:
                print(f"  [!] Ollama error (attempt {attempt + 1}): {e}")

            if attempt < self._retry_count:
                time.sleep(self._retry_delay)

        print("  [!] All LLM extraction attempts failed")
        return None
