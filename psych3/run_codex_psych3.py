"""psych3 的 codex 入口（a，2026-10-19）。

`../vs-pilot/subject.py` 把 codex-cli 版本固定在 δ-NLI 当时的 0.162（EXPECTED_VERSION），那个档案进 δ-NLI 的指纹，不能改。
psych3 是另一个实验：这里只把 EXPECTED_VERSION 换成 `codex_pin.json` 的版本，其余检查（登录方式、隔离参数、事件流与
污染判定）完全沿用。实际版本由 freeze() 写进 subject meta，因而进 psych3 的实验指纹；版本与 pin 不符时照旧拒绝。

用法（与 run_psych3.py 相同的参数，只用于 codex 配置）：
    ..\\suppression\\llm_python.cmd -I -X utf8 -B run_codex_psych3.py <dev|formal> codex [--exp ...] [--workers N]
"""
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PIN = json.loads((HERE / "codex_pin.json").read_text(encoding="utf-8"))["version"]


def pin_version():
    """在 codex_subject 导入前载入 vs-pilot 的 subject 模块并替换版本；返回该模块。"""
    sys.path.insert(0, str(HERE.parent / "vs-pilot"))
    import subject  # noqa: E402  ../vs-pilot/subject.py（codex_subject 以同名导入，取得同一个模块物件）
    subject.EXPECTED_VERSION = PIN
    return subject


def recheck_each_call(subject):
    """c 审（10-19）：freeze() 只在启动时查版本；这里让每次调用前再查一次，不符就抛错（外壳按调用异常停下）。"""
    sys.path.insert(0, str(HERE.parent / "dnli"))
    import codex_subject  # noqa: E402
    original = codex_subject.CodexSubject.call
    if getattr(original, "_psych3_version_checked", False):
        return codex_subject

    def call(self, prompt, tag, *args, **kwargs):
        ver = "".join(subject._run_small(self.exe, ["--version"])).strip()
        if ver != PIN:
            raise RuntimeError("codex version changed during run: %r (pinned %r)" % (ver, PIN))
        return original(self, prompt, tag, *args, **kwargs)

    call._psych3_version_checked = True
    codex_subject.CodexSubject.call = call
    return codex_subject


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) < 2 or argv[1] != "codex":
        print("REFUSED: run_codex_psych3.py 只用于 codex 配置")
        return 2
    recheck_each_call(pin_version())
    sys.path.insert(0, str(HERE))
    import run_psych3  # noqa: E402
    return run_psych3.main(argv)


if __name__ == "__main__":
    sys.exit(main())
