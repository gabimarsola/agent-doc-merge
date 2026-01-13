#!/usr/bin/env python3

import argparse
import datetime
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple


PACKAGE_JSON = "package.json"
PYPROJECT_TOML = "pyproject.toml"
POM_XML = "pom.xml"
CARGO_TOML = "Cargo.toml"


def sh(cmd: List[str]) -> str:
    return subprocess.check_output(cmd, text=True).strip()


def sh_allow_fail(cmd: List[str]) -> Tuple[int, str]:
    p = subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    return p.returncode, (p.stdout or "").strip()


def safe_ref(ref: str) -> str:
    ref = (ref or "").strip()
    if not ref:
        return ""
    if re.fullmatch(r"[0-9a-fA-F]{7,40}", ref):
        return ref
    # allow refs like HEAD~1 etc.
    return ref


def repo_dir_name(repository: str) -> str:
    repository = (repository or "").strip()
    name = repository.split("/")[-1] if repository else "repository"
    name = re.sub(r"[^0-9A-Za-z._-]+", "_", name)
    return name or "repository"


def _version_from_package_json(path: Path) -> str:
    if not path.exists():
        return ""
    import json

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        v = str(data.get("version", "")).strip()
        return v
    except Exception:
        return ""


def _version_from_pyproject(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")

    m = re.search(r"(?m)^version\s*=\s*\"([^\"]+)\"\s*$", text)
    if m:
        return m.group(1).strip()

    m = re.search(r"(?ms)^\[project\].*?^version\s*=\s*\"([^\"]+)\"\s*$", text)
    if m:
        return m.group(1).strip()

    return ""


def _version_from_pom(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8", errors="ignore")
    m = re.search(r"<version>([^<]+)</version>", text)
    return m.group(1).strip() if m else ""


def _version_from_cargo(path: Path) -> str:
    if not path.exists():
        return ""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"(?m)^version\s*=\s*\"([^\"]+)\"\s*$", text)
    return m.group(1).strip() if m else ""


def _version_from_git_tag() -> str:
    rc, out = sh_allow_fail(["git", "describe", "--tags", "--abbrev=0"])
    return out if rc == 0 and out else ""


def detect_version() -> str:
    """Best-effort version detection without assuming a specific stack."""
    v = _version_from_package_json(Path(PACKAGE_JSON))
    if v:
        return v

    v = _version_from_pyproject(Path(PYPROJECT_TOML))
    if v:
        return v

    v = _version_from_pom(Path(POM_XML))
    if v:
        return v

    v = _version_from_cargo(Path(CARGO_TOML))
    if v:
        return v

    v = _version_from_git_tag()
    if v:
        return v

    return "0.0.0"


@dataclass
class ChangeSummary:
    commits: List[str]
    files_changed: List[str]


def summarize_changes(before: str, after: str) -> ChangeSummary:
    before = safe_ref(before)
    after = safe_ref(after)

    # If before is all zeros (first push), compare with empty tree by listing commits only.
    if before == "0000000000000000000000000000000000000000" or not before:
        log_range = after
        diff_range = after
    else:
        log_range = f"{before}..{after}"
        diff_range = f"{before}..{after}"

    commits_out = ""
    if log_range:
        rc, out = sh_allow_fail(["git", "log", "--no-merges", "--pretty=format:%s", log_range])
        commits_out = out if rc == 0 else ""
    commits = [c.strip() for c in commits_out.splitlines() if c.strip()]

    files_out = ""
    if diff_range:
        rc, out = sh_allow_fail(["git", "diff", "--name-only", diff_range])
        files_out = out if rc == 0 else ""
    files_changed = [f.strip() for f in files_out.splitlines() if f.strip()]

    return ChangeSummary(commits=commits, files_changed=files_changed)


def guess_description(summary: ChangeSummary) -> str:
    if summary.commits:
        return "\n".join([f"- {c}" for c in summary.commits[:30]])
    if summary.files_changed:
        return "\n".join([f"- Atualização em `{f}`" for f in summary.files_changed[:30]])
    return "- Alterações do merge não puderam ser inferidas automaticamente."


def make_markdown(title: str, version: str, description_md: str) -> str:
    return (
        f"# {title} (v{version})\n\n"
        f"## Descrição das alterações\n\n"
        f"{description_md}\n\n"
        f"## Regras de negócio e técnicas\n\n"
        f"- (Preencher)\n\n"
        f"## Exemplos de utilização da mudança realizada\n\n"
        f"- (Preencher)\n\n"
        f"## Forma de testar essa mudança\n\n"
        f"- (Preencher)\n"
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--before", required=True)
    ap.add_argument("--after", required=True)
    ap.add_argument("--repository", required=False, default="")
    ap.add_argument("--output-dir", required=True)
    args = ap.parse_args()

    version = detect_version()

    summary = summarize_changes(args.before, args.after)
    description = guess_description(summary)

    date_str = datetime.datetime.now(datetime.UTC).strftime("%d%m%Y")

    title = f"v{version} - {date_str}"

    out_dir = Path(args.output_dir) / repo_dir_name(args.repository)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_version = re.sub(r"[^0-9A-Za-z._-]+", "_", version)
    out_file = out_dir / f"v{safe_version}-{date_str}.md"

    out_file.write_text(make_markdown(title=title, version=version, description_md=description), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
