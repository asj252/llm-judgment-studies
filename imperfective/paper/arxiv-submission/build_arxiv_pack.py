#!/usr/bin/env python3
"""Build the seven-file arXiv archive and verify it in a fresh TeX directory.

Run: PYTHONUTF8=1 PYTHONDONTWRITEBYTECODE=1 python3 -X utf8 -B build_arxiv_pack.py
Only archive and metadata deliverables next to this script are written; TeX runs in /tmp.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import tarfile
import tempfile

HERE = Path(__file__).resolve().parent
PAPER = HERE.parent
SOURCES = tuple(sorted((
    "acl_natbib.bst",
    "paper.tex", "paper.bbl",
    "figures/fig1_act1_collapse.pdf",
    "figures/fig2_act2_realis_paradox.pdf",
    "figures/fig3_act3_directional_reversal.pdf",
    "figures/fig4_act4_mcw_minus_mcu.pdf",
)))


def require(ok, message):
    if not ok:
        raise RuntimeError(message)


def fingerprint(path):
    content = path.read_bytes()
    return {"sha256": hashlib.sha256(content).hexdigest(), "bytes": len(content)}


def metadata():
    tex = (PAPER / "paper.tex").read_text(encoding="utf-8")
    titles = re.findall(r"\\title\{([^{}\n]+)\}", tex)
    require(len(titles) == 1, "Expected exactly one plain-text TeX title")
    guide = (PAPER / "ARXIV_SUBMISSION_GUIDE.md").read_text(encoding="utf-8")

    def field(name):
        sections = re.findall(r"^### " + re.escape(name) + r"[^\n]*\n(.*?)(?=^### |^## |\Z)", guide, re.M | re.S)
        require(len(sections) == 1, "Expected exactly one guide section: " + name)
        blocks = re.findall(r"```text\n(.*?)\n```", sections[0], re.S)
        require(len(blocks) == 1, "Expected exactly one guide field: " + name)
        return blocks[0].strip()

    abstract = field("Abstract")
    require(1700 <= len(abstract) <= 1920, f"Abstract length invalid: {len(abstract)}")
    require(not re.search(r"\\[A-Za-z]+|[$]", abstract), "Abstract contains LaTeX")
    require(field("Title") == titles[0], "Guide and TeX titles differ")
    return {"title.txt": titles[0], "abstract.txt": abstract, "comments.txt": field("Comments")}


def normalized(info):
    info.uid = info.gid = info.mtime = 0
    info.uname = info.gname = ""
    info.mode = 0o644
    info.pax_headers = {}
    return info


def archive_sources(target):
    # Streaming tarfile uses a gzip header with an empty fixed filename. Its
    # four-byte MTIME is the only clock-dependent field; RFC 1952 permits zero.
    with target.open("wb") as stream:
        with tarfile.open(name="", mode="w|gz", fileobj=stream, format=tarfile.USTAR_FORMAT) as archive:
            for name in SOURCES:
                archive.add(PAPER / name, arcname=name, recursive=False, filter=normalized)
    with target.open("r+b") as stream:
        require(stream.read(4) == b"\x1f\x8b\x08\x08", "Unexpected gzip header")
        stream.write(bytes(4))
    with tarfile.open(target, "r:gz") as archive:
        require(archive.getnames() == list(SOURCES), "Unexpected archive members/order")
        require(all(m.isfile() for m in archive.getmembers()), "Non-file member")


def log_counts(text):
    return {
        "latex_errors": len(re.findall(r"^!|LaTeX Error:|Fatal error occurred", text, re.M)),
        "overfull_hbox": text.count(r"Overfull \hbox"),
        "undefined_references": len(re.findall(
            r"(?:Reference|Citation)[^\n]*undefined|There were undefined (?:references|citations)", text)),
    }


def compile_archive(target):
    engine = shutil.which("pdflatex")
    pdfinfo = shutil.which("pdfinfo")
    require(engine and pdfinfo, "pdflatex and pdfinfo must be installed")
    with tempfile.TemporaryDirectory(prefix="arxiv-autotex-") as tmp:
        work = Path(tmp)
        require(not list(work.iterdir()), "Compilation directory was not empty")
        with tarfile.open(target, "r:gz") as archive:
            require(archive.getnames() == list(SOURCES), "Unsafe archive contents")
            # Members were checked against the fixed relative whitelist above.
            require(all(member.isfile() for member in archive.getmembers()), "Unsafe non-file member")
            archive.extractall(work, members=archive.getmembers())
        require(sorted(p.relative_to(work).as_posix() for p in work.rglob("*") if p.is_file()) == list(SOURCES),
                "Extraction is not exactly the seven source files")
        # Isolate user TeX trees/search overrides as well as the working directory.
        env = {"PATH": str(Path(engine).parent) + ":/usr/bin:/bin",
               "HOME": tmp, "TEXMFHOME": str(work / "texmf-home"),
               "TEXMFVAR": str(work / "texmf-var"), "LC_ALL": "C.UTF-8"}
        command = [engine, "-interaction=nonstopmode", "-halt-on-error", "paper.tex"]
        passes = []
        for number in (1, 2):
            result = subprocess.run(command, cwd=work, env=env, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=180)
            log = (work / "paper.log").read_text(encoding="utf-8", errors="replace") if (work / "paper.log").exists() else result.stdout
            counts = log_counts(log)
            passes.append({"pass": number, "exit_code": result.returncode, **counts})
            require(result.returncode == 0, "pdflatex failed: " + result.stdout[-6000:] + result.stderr)
            require(counts["latex_errors"] == counts["overfull_hbox"] == 0,
                    "LaTeX errors or overfull hboxes: " + json.dumps(passes[-1]))
        require(passes[-1]["undefined_references"] == 0, "Unresolved references after two passes")
        require(".deps/" not in log, "Local .deps dependency detected")
        info = subprocess.run([pdfinfo, "paper.pdf"], cwd=work, env=env,
                              capture_output=True, text=True, encoding="utf-8", check=True, timeout=30).stdout
        pages = re.search(r"^Pages:\s+(\d+)", info, re.M)
        require(pages and int(pages[1]) == 21, "PDF must have exactly 21 pages")
        return {"fresh_empty_directory": True, "isolated_user_tex_environment": True,
                "command": ["pdflatex", *command[1:]], "passes": passes, "pdf_pages": int(pages[1]),
                "final_log": log_counts(log), "passed": True}


def main():
    for name in SOURCES:
        require((PAPER / name).is_file() and (PAPER / name).stat().st_size > 0,
                "Required source missing or empty: " + name)
    before = {name: fingerprint(PAPER / name) for name in SOURCES}
    fields = metadata()
    target = HERE / "arxiv-source.tar.gz"
    archive_sources(target)
    compiled = compile_archive(target)
    require(before == {name: fingerprint(PAPER / name) for name in SOURCES}, "Sources changed during build")
    for name, value in fields.items():
        (HERE / name).write_text(value, encoding="utf-8")
    manifest = {"sources": before, "archive": {"path": target.name, **fingerprint(target)},
                "metadata": {name: {"characters": len(value)} for name, value in fields.items()},
                "autotex": compiled}
    (HERE / "manifest_arxiv.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("ARCHIVE: exactly 7 files; normalized tar/gzip metadata PASS")
    print("SOURCE SHA-256: 7/7 unchanged PASS")
    for name, value in fields.items():
        print(f"METADATA {name}: {len(value)} characters PASS")
    for item in compiled["passes"]:
        print("AUTOTEX: " + json.dumps(item, sort_keys=True))
    print("AUTOTEX FINAL: " + json.dumps(compiled["final_log"], sort_keys=True) + "; PDF pages=21 PASS")
    print("ARCHIVE SHA-256: " + manifest["archive"]["sha256"])
    print("ALL ARXIV PACK CHECKS PASSED")


if __name__ == "__main__":
    main()
