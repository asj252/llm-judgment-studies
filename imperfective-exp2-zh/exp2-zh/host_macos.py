"""macOS host adapter for Experiment 2 (adapted from exp1-en/host_macos.py).

Paths come only from host_paths_<host_id>.json beside this file. busy_check is a
conservative stand-in: macOS cannot report per-process GPU use without sudo, so
names, command lines, RSS and %CPU decide; anything unparseable is not idle.
No process is ever killed except the server this host started.
"""
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from host import terminate_process

ROOT = Path(__file__).resolve().parent
PS_COMMAND = ["ps", "-axo", "pid=,rss=,%cpu=,comm=,args="]
VM_STAT_COMMAND = ["vm_stat"]
PAGESIZE_COMMAND = ["sysctl", "-n", "hw.pagesize"]
COMMAND_TIMEOUT = 10
BUSY_NAMES = ("llama-server", "llama-cli", "ollama", "LM Studio", "lms")
BUSY_WORDS = ("mlx", "torch", "llama", "ollama", "vllm", "transformers", "diffusers")
LOCAL_WORDS = ("venvs/ntl", "ntl_python", "name-that-llm")
REMOTE_CLI_MARKERS = ("google-colab-cli/bin/python",)
RSS_LIMIT_KIB = 4 * 1024 * 1024
CPU_LIMIT = 50.0
FREE_LIMIT = 12 * 1024 ** 3
VM_FIELDS = ("Pages free", "Pages inactive", "Pages speculative")
COMM_WIDTH = 16
TOKENIZER_FILES = ("tokenizer.json", "tokenizer_config.json")
IDENTITY_KEYS = ("port", "gguf_sha256", "server_sha256", "tokenizer_sha256", "llama_cpp_version",
                 "transformers_version", "chat_template_sha256", "service", "server_parameters")
PATH_KEYS = ("host_id", "llama_server", "gguf_dir", "hf_home", "port")
SERVICE_KEYS = ("build_info", "model_path")
HOST_ID_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_.")
LINE = re.compile(rb"\s*(\d+)\s+(\d+)\s+(\d+(?:\.\d+)?) (.*)", re.S)
NAME_IN_ARGS = re.compile(r"(?:^|/)(?:" + "|".join(re.escape(n) for n in BUSY_NAMES) + r"|mlx[^/\s]*)(?=\s|$)")


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def parse_ps(raw):
    """Rows of (pid, rss KiB, %cpu, comm, args); raises ValueError on any unexpected line."""
    rows = []
    for line in raw.splitlines():
        if not line.strip():
            continue
        match = LINE.fullmatch(line)
        rest = match.group(4) if match else b""
        if not match or len(rest) <= COMM_WIDTH + 1 or rest[COMM_WIDTH:COMM_WIDTH + 1] != b" ":
            raise ValueError("unparseable ps line: " + line.decode("utf-8", "replace"))
        rows.append({"pid": int(match.group(1)), "rss_kib": int(match.group(2)), "cpu": float(match.group(3)),
                     "comm": rest[:COMM_WIDTH].decode("utf-8", "replace").rstrip(),
                     "args": rest[COMM_WIDTH + 1:].decode("utf-8", "replace")})
    if not rows:
        raise ValueError("empty ps output")
    return rows


def flag_process(row):
    """Reasons a process blocks startup; empty when it looks harmless."""
    reasons = []
    name = row["comm"].rsplit("/", 1)[-1]
    if name in BUSY_NAMES or name.startswith("mlx") or NAME_IN_ARGS.search(row["args"]):
        reasons.append("name")
    lowered = row["args"].lower()
    is_remote_colab_cli = any(m in lowered for m in REMOTE_CLI_MARKERS) and not any(
        w in lowered for w in ("venvs/ntl", "ntl_python")
    )
    local_words = tuple(w for w in LOCAL_WORDS if not (is_remote_colab_cli and w == "name-that-llm"))
    words = [w for w in BUSY_WORDS + local_words if w.lower() in lowered]
    if words:
        reasons.append("args:" + ",".join(words))
    if row["rss_kib"] >= RSS_LIMIT_KIB:
        reasons.append("rss>=4GiB")
    if row["cpu"] >= CPU_LIMIT:
        reasons.append("cpu>=50")
    return reasons


def parse_available(vm_text, pagesize_text):
    """(free + inactive + speculative) pages x page size; purgeable is excluded on purpose."""
    pagesize = int(pagesize_text.strip())
    if pagesize <= 0:
        raise ValueError("invalid page size")
    pages = {}
    for line in vm_text.splitlines():
        key, sep, value = line.partition(":")
        if sep and key.strip() in VM_FIELDS:
            pages[key.strip()] = int(value.strip().rstrip("."))
    if set(pages) != set(VM_FIELDS):
        raise ValueError("vm_stat fields missing: " + ", ".join(sorted(set(VM_FIELDS) - set(pages))))
    return sum(pages.values()) * pagesize


def evaluate_busy(ps_raw, vm_text, pagesize_text, self_pid):
    """Pure decision on captured command output; any parsing problem means not idle."""
    detail = {"vm_stat": vm_text, "pagesize": pagesize_text}
    try:
        rows = parse_ps(ps_raw)
    except ValueError as exc:
        return False, {**detail, "reason": "ps: " + str(exc)}
    flagged = [{**row, "reasons": reasons} for row in rows if row["pid"] != self_pid
               for reasons in [flag_process(row)] if reasons]
    detail["processes"] = flagged
    try:
        available = parse_available(vm_text, pagesize_text)
    except (ValueError, AttributeError) as exc:
        return False, {**detail, "reason": "memory: " + str(exc)}
    detail["available_bytes"] = available
    if flagged:
        return False, {**detail, "reason": "possible compute processes; verify manually"}
    if available < FREE_LIMIT:
        return False, {**detail, "reason": "available memory below 12 GiB"}
    return True, {**detail, "reason": "idle"}


def capture(run, command, timeout=COMMAND_TIMEOUT, merge_stderr=False):
    """stdout bytes (optionally with stderr) of a successful command; raises on failure or timeout."""
    streams = {"stdout": subprocess.PIPE, "stderr": subprocess.STDOUT} if merge_stderr else {"capture_output": True}
    result = run(command, stdin=subprocess.DEVNULL, timeout=timeout, check=False, **streams)
    if result.returncode != 0:
        raise OSError(f"{command[0]} exited {result.returncode}")
    return result.stdout


def available_memory(run=subprocess.run):
    vm_text = capture(run, VM_STAT_COMMAND).decode("utf-8", "replace")
    return parse_available(vm_text, capture(run, PAGESIZE_COMMAND).decode("utf-8", "replace"))


class MacHost:
    def __init__(self, paths, *, discovery=False, run=subprocess.run, self_pid=os.getpid, kill=os.kill,
                 load_tokenizer=None, transformers_version=None):
        self.paths, self.discovery = paths, discovery
        self.host_id, self.port = paths["host_id"], paths["port"]
        self.run, self.self_pid, self.kill = run, self_pid, kill
        self._load_tokenizer, self._transformers_version = load_tokenizer, transformers_version
        self._cache = {}

    def _port_for(self, model_cfg):
        if "port" not in model_cfg:
            return self.port
        if model_cfg["port"] != self.port or type(model_cfg["port"]) is not int:
            raise ValueError(f"model_cfg port {model_cfg['port']!r} conflicts with host_paths port {self.port}")
        return self.port

    def server_command(self, model_cfg):
        port = self._port_for(model_cfg)
        return [self.paths["llama_server"], "-m", str(Path(self.paths["gguf_dir"]) / model_cfg["gguf"]),
                "--port", str(port), "-c", str(model_cfg["ctx"]), "-ngl", "999", "--parallel", "1",
                "--host", "127.0.0.1", "--no-webui", "--seed", "0"]

    def server_env(self):
        return dict(os.environ)

    def busy_check(self):
        captured = {}
        for key, command in (("ps", PS_COMMAND), ("vm_stat", VM_STAT_COMMAND), ("pagesize", PAGESIZE_COMMAND)):
            try:
                captured[key] = capture(self.run, command)
            except (OSError, subprocess.SubprocessError) as exc:
                return False, {"reason": f"{key} failed: {type(exc).__name__}: {exc}"}
        return evaluate_busy(captured["ps"], captured["vm_stat"].decode("utf-8", "replace"),
                             captured["pagesize"].decode("utf-8", "replace"), self.self_pid())

    def _key(self, path):
        stat = Path(path).stat()
        return str(path), stat.st_size, stat.st_mtime_ns, stat.st_ino

    def _cached(self, kind, key, compute):
        if (kind, key) not in self._cache:
            self._cache[(kind, key)] = compute()
        return self._cache[(kind, key)]

    def _hash(self, path):
        return self._cached("sha256", self._key(path), lambda: file_sha256(path))

    def tokenizer_dir(self, model_cfg):
        return (Path(self.paths["hf_home"]) / "hub" / ("models--" + model_cfg["repo"].replace("/", "--")) /
                "snapshots" / model_cfg["commit"])

    def _version(self, server):
        def compute():
            out = capture(self.run, [str(server), "--version"], timeout=60, merge_stderr=True)
            lines = [line.strip() for line in out.decode("utf-8", "replace").splitlines() if line.strip().startswith("version:")]
            if len(lines) != 1:
                raise ValueError("llama-server --version has no single version line")
            return lines[0]
        return self._cached("version", self._key(server), compute)

    def _template_hash(self, model_cfg, folder):
        def compute():
            loader = self._load_tokenizer
            if loader is None:
                if Path(os.environ.get("HF_HOME", "")).resolve() != Path(self.paths["hf_home"]).resolve():
                    raise ValueError("HF_HOME must equal host_paths hf_home")
                from check_tokens import load_tokenizer as loader
            tok, _ = loader({k: v for k, v in model_cfg.items() if k != "port"})
            if not isinstance(tok.chat_template, str):
                raise ValueError("tokenizer has no chat template")
            return hashlib.sha256(tok.chat_template.encode("utf-8")).hexdigest()
        return self._cached("template", tuple(self._key(folder / name) for name in TOKENIZER_FILES), compute)

    def transformers_version(self):
        if self._transformers_version is not None:
            return self._transformers_version()
        import transformers
        return transformers.__version__

    def asset_identity(self, model_cfg):
        if self.discovery:
            raise ValueError("discovery-mode host cannot provide asset identity")
        command = self.server_command(model_cfg)
        server = Path(self.paths["llama_server"]).resolve()
        folder = self.tokenizer_dir(model_cfg)
        return {"port": self.port,
                "gguf_sha256": self._hash(Path(self.paths["gguf_dir"]) / model_cfg["gguf"]),
                "server_sha256": self._hash(server),
                "tokenizer_sha256": {name: self._hash(folder / name) for name in TOKENIZER_FILES},
                "llama_cpp_version": self._version(server),
                "transformers_version": self.transformers_version(),
                "chat_template_sha256": self._template_hash(model_cfg, folder),
                "service": {k: self.paths["service_expected"][k] for k in SERVICE_KEYS},
                "server_parameters": command}

    def terminate(self, proc):
        return terminate_process(proc)

    def pid_alive(self, pid):
        try:
            self.kill(pid, 0)
        except ProcessLookupError:
            return False
        except Exception:
            return True
        return True


def valid_service(value):
    return (isinstance(value, dict) and set(value) == set(SERVICE_KEYS) and
            all(isinstance(value[k], str) and value[k].strip() for k in SERVICE_KEYS))


def load_paths(host_id, discovery=False, paths_file=None):
    if not host_id or any(c not in HOST_ID_CHARS for c in host_id):
        raise ValueError("invalid host_id")
    path = Path(paths_file) if paths_file is not None else ROOT / ("host_paths_" + host_id + ".json")
    if not path.is_file():
        raise ValueError(f"host paths file missing: {path.name}")
    paths = json.loads(path.read_text(encoding="utf-8"))
    missing = [k for k in PATH_KEYS if k not in paths]
    if missing:
        raise ValueError("host paths missing fields: " + ", ".join(missing))
    if paths["host_id"] != host_id:
        raise ValueError("host_id in host paths does not match")
    if type(paths["port"]) is not int or not 1024 <= paths["port"] <= 65535:
        raise ValueError("port must be an integer in [1024, 65535]")
    server = Path(paths["llama_server"])
    if not server.is_file() or not os.access(server, os.X_OK):
        raise ValueError("llama_server missing or not executable")
    for key in ("gguf_dir", "hf_home"):
        if not Path(paths[key]).is_dir():
            raise ValueError(f"{key} does not exist")
    if not discovery and not valid_service(paths.get("service_expected")):
        raise ValueError("service_expected must hold two non-empty strings; run discovery first")
    return paths


def make_host(host_id, discovery=False, *, paths_file=None, **inject):
    return MacHost(load_paths(host_id, discovery, paths_file), discovery=discovery, **inject)
