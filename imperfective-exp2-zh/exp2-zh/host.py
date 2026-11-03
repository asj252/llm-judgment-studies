"""Injectable host boundary; real macOS implementation is in host_macos.py."""
import os
import subprocess
from typing import Protocol


class Host(Protocol):
    host_id: str
    def server_command(self, model_cfg) -> list[str]: ...
    def server_env(self) -> dict: ...
    def busy_check(self) -> tuple[bool, object]: ...
    def asset_identity(self, model_cfg) -> dict: ...
    def terminate(self, proc): ...
    def pid_alive(self, pid: int) -> bool: ...


def terminate_process(proc):
    if proc is None:
        return None
    if proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=30)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=30)
    return proc.returncode


class FakeProcess:
    def __init__(self):
        self.returncode = None
        self.pid = os.getpid()
        self.terminations = 0
    def poll(self):
        return self.returncode
    def terminate(self):
        self.terminations += 1
        self.returncode = 0
    def kill(self):
        self.returncode = -9
    def wait(self, timeout=30):
        return self.returncode


class FakeHost:
    def __init__(self, host_id="dry", busy=(True, "fake idle"), identity=None):
        self.host_id, self.busy = host_id, busy
        self.identity = identity or {"gguf_sha256": "dry-gguf", "server_sha256": "dry-server",
            "tokenizer_sha256": {"tokenizer.json": "dry-tokenizer", "tokenizer_config.json": "dry-config"},
            "llama_cpp_version": "dry-build", "transformers_version": "dry-version",
            "chat_template_sha256": "dry-template", "service": {"build_info": "dry-build", "model_path": "dry-model"},
            "server_parameters": ["fake-server", "--parallel", "1"]}
        self.terminated = []
    def server_command(self, model_cfg):
        return list(self.identity["server_parameters"])
    def server_env(self):
        return dict(os.environ)
    def busy_check(self):
        return self.busy
    def pid_alive(self, pid):
        # Fake ownership only; real hosts inject their own process query.
        return pid == os.getpid()
    def asset_identity(self, model_cfg):
        return self.identity.copy()
    def terminate(self, proc):
        code = terminate_process(proc)
        if proc not in self.terminated:
            self.terminated.append(proc)
        return code
