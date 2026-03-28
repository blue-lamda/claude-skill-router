#!/usr/bin/env python3
"""
install_skill.py — One-command skill installer.
Handles .skill files, GitHub repos, and local directories.
Always runs update_router.py after a successful install.

Usage:
    python install_skill.py path/to/skill.skill
    python install_skill.py https://github.com/user/repo
    python install_skill.py https://github.com/user/repo --subdir skills/my-skill
    python install_skill.py ./local-skill-folder

Options:
    --skills-dir    Where to install (default: ~/.claude/skills/user)
    --subdir        Subdirectory within a GitHub repo containing the skill
    --no-update     Skip running update_router.py after install
    --skip-scan     Skip pre-install security scan (not recommended)
    --strict-scan   Block install on MEDIUM findings too (default: HIGH/CRITICAL only)
"""

import os
import re
import sys
import shutil
import zipfile
import tempfile
import argparse
import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlretrieve
from urllib.parse import urlparse

SCRIPT_DIR = Path(__file__).parent
UPDATE_SCRIPT = SCRIPT_DIR / "update_router.py"
ROUTER_SKILL = SCRIPT_DIR.parent / "SKILL.md"
DEFAULT_SKILLS_DIR = Path(os.path.expanduser("~/.claude/skills"))

# Only allow safe characters in skill names used as directory names
_SAFE_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')
# Only allow safe characters in GitHub owner/repo identifiers
_SAFE_IDENT_RE = re.compile(r'^[a-zA-Z0-9_.-]+$')


def _run_scan(path: Path, strict: bool) -> bool:
    """Run scan_skill.py. Returns True if safe to proceed, False if blocked."""
    scan_script = SCRIPT_DIR / "scan_skill.py"
    if not scan_script.exists():
        print("  [warn] scan_skill.py not found — skipping security scan.")
        return True

    cmd = [sys.executable, str(scan_script), str(path)]
    if strict:
        cmd.append("--strict")

    print("\nRunning security scan...")
    result = subprocess.run(cmd, check=False)  # nosec B603

    if result.returncode == 2:
        print("\n[blocked] HIGH or CRITICAL findings detected. Install aborted.")
        print("  Review the findings above and only install from trusted sources.")
        print("  Use --skip-scan to bypass (not recommended).")
        return False
    if result.returncode == 1:
        print("\n[blocked] MEDIUM findings detected (--strict-scan is active). Install aborted.")
        return False
    return True


def _safe_name(name: str) -> str | None:
    """Return name if safe to use as a directory name, else None."""
    if _SAFE_NAME_RE.match(name):
        return name
    return None


def _extract_zip_safe(z: zipfile.ZipFile, dest: Path, prefix: str):
    """Extract zip entries, rejecting any path that escapes dest (Zip Slip)."""
    dest_resolved = dest.resolve()
    for member in z.namelist():
        stripped = member[len(prefix):] if prefix else member
        if not stripped:
            continue
        out_path = (dest / stripped).resolve()
        if not str(out_path).startswith(str(dest_resolved)):
            print(f"  [blocked] Zip Slip detected: '{member}' would escape install directory. Aborting.")
            shutil.rmtree(dest, ignore_errors=True)
            sys.exit(2)
        if member.endswith("/"):
            out_path.mkdir(parents=True, exist_ok=True)
        else:
            out_path.parent.mkdir(parents=True, exist_ok=True)
            with z.open(member) as src, open(out_path, "wb") as dst:
                dst.write(src.read())


def install_skill_file(skill_file: Path, target_dir: Path, skip_scan: bool, strict_scan: bool) -> Path:
    """Unzip a .skill file into target_dir/skill_name/."""
    # Scan zip before extraction
    if not skip_scan:
        if not _run_scan(skill_file, strict_scan):
            return None

    skill_name = skill_file.stem
    dest = target_dir / skill_name

    if dest.exists():
        print(f"  [warn] {skill_name} already exists at {dest}")
        answer = input("  Overwrite? [y/N] ").strip().lower()
        if answer != "y":
            print("  Skipping install.")
            return None
        shutil.rmtree(dest)

    dest.mkdir(parents=True, exist_ok=True)

    with zipfile.ZipFile(skill_file, "r") as z:
        members = z.namelist()
        prefix = members[0] if members and members[0].endswith("/") else ""
        _extract_zip_safe(z, dest, prefix)

    print(f"  [ok] Installed {skill_name} to {dest}")
    return dest


def install_github_repo(
    repo_url: str, target_dir: Path, subdir: str | None,
    skip_scan: bool, strict_scan: bool
) -> Path:
    """Download a GitHub repo zip and install the skill from it."""
    parsed = urlparse(repo_url)
    if parsed.scheme != "https" or parsed.netloc not in ("github.com", "www.github.com"):
        print(f"[error] Only https://github.com URLs are supported: {repo_url}")
        sys.exit(1)

    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        print(f"[error] Invalid GitHub URL: {repo_url}")
        sys.exit(1)

    owner, repo = path_parts[0], path_parts[1].replace(".git", "")

    # Validate owner/repo to prevent URL manipulation
    if not _SAFE_IDENT_RE.match(owner) or not _SAFE_IDENT_RE.match(repo):
        print(f"[error] Unsafe characters in GitHub owner/repo: '{owner}/{repo}'")
        sys.exit(1)

    # Validate subdir to prevent path traversal
    if subdir:
        parts = Path(subdir).parts
        if any(p == ".." for p in parts) or subdir.startswith("/"):
            print(f"[error] --subdir must not contain '..' or absolute paths: '{subdir}'")
            sys.exit(1)

    zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"
    print(f"  Downloading {owner}/{repo}...")

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / f"{repo}.zip"

        try:
            urlretrieve(zip_url, zip_path)  # nosec B310 — URL validated as https://github.com above
        except URLError:
            zip_url = zip_url.replace("/main.zip", "/master.zip")
            try:
                urlretrieve(zip_url, zip_path)  # nosec B310
            except URLError as e:
                print(f"[error] Could not download repo: {e}")
                sys.exit(1)

        extract_dir = Path(tmp) / "extracted"
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)

        extracted_roots = list(extract_dir.iterdir())
        if not extracted_roots:
            print("[error] Empty archive.")
            sys.exit(1)
        repo_root = extracted_roots[0]

        skill_source = repo_root / subdir if subdir else repo_root

        if not skill_source.exists():
            print(f"[error] Subdir not found in repo: {subdir}")
            sys.exit(1)

        if not (skill_source / "SKILL.md").exists():
            print(f"[warn] No SKILL.md found in {skill_source}")
            print("  This may not be a valid skill directory.")
            answer = input("  Continue anyway? [y/N] ").strip().lower()
            if answer != "y":
                sys.exit(0)

        # Scan extracted directory before copying
        if not skip_scan:
            if not _run_scan(skill_source, strict_scan):
                return None

        raw_name = _get_skill_name(skill_source) or repo
        skill_name = _safe_name(raw_name)
        if not skill_name:
            print(f"[error] Unsafe skill name '{raw_name}' — contains characters not allowed in directory names.")
            print("  Rename the 'name:' field in the skill's SKILL.md to use only [a-zA-Z0-9_-].")
            sys.exit(1)

        dest = target_dir / skill_name

        if dest.exists():
            print(f"  [warn] {skill_name} already exists at {dest}")
            answer = input("  Overwrite? [y/N] ").strip().lower()
            if answer != "y":
                print("  Skipping install.")
                return None
            shutil.rmtree(dest)

        # symlinks=True preserves symlinks rather than following them
        shutil.copytree(skill_source, dest, symlinks=True)
        print(f"  [ok] Installed {skill_name} to {dest}")
        return dest


def install_local_dir(source: Path, target_dir: Path, skip_scan: bool, strict_scan: bool) -> Path:
    """Install a skill from a local directory."""
    if not (source / "SKILL.md").exists():
        print(f"[warn] No SKILL.md found in {source}")

    if not skip_scan:
        if not _run_scan(source, strict_scan):
            return None

    raw_name = _get_skill_name(source) or source.name
    skill_name = _safe_name(raw_name)
    if not skill_name:
        print(f"[error] Unsafe skill name '{raw_name}' — use only [a-zA-Z0-9_-] in the 'name:' field.")
        sys.exit(1)

    dest = target_dir / skill_name

    if dest.exists():
        print(f"  [warn] {skill_name} already exists at {dest}")
        answer = input("  Overwrite? [y/N] ").strip().lower()
        if answer != "y":
            return None
        shutil.rmtree(dest)

    shutil.copytree(source, dest, symlinks=True)
    print(f"  [ok] Installed {skill_name} to {dest}")
    return dest


def _get_skill_name(skill_dir: Path) -> str | None:
    """Extract name from SKILL.md frontmatter."""
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return None
    try:
        content = skill_md.read_text(encoding="utf-8")
        match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
        if match:
            name_match = re.search(r"^name:\s*(.+)$", match.group(1), re.MULTILINE)
            if name_match:
                return name_match.group(1).strip()
    except OSError as e:
        print(f"  [warn] Could not read {skill_md}: {e}")
    return None


def run_update(skills_dir: Path):
    """Trigger update_router.py after install."""
    root_skills_dir = skills_dir.parent if skills_dir.name == "user" else skills_dir

    cmd = [
        sys.executable,
        str(UPDATE_SCRIPT),
        "--skills-dir", str(root_skills_dir),
        "--router-path", str(ROUTER_SKILL),
    ]
    print("\nUpdating skill router...")
    try:
        result = subprocess.run(cmd, check=False, timeout=30)  # nosec B603
        if result.returncode == 0:
            print("[ok] Router updated.")
        else:
            print("[warn] Router update finished with errors. Check output above.")
    except subprocess.TimeoutExpired:
        print("[warn] Router update timed out.")
    except OSError as e:
        print(f"[warn] Could not run update_router.py: {e}")


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Install a Claude skill from a file, GitHub repo, or local dir."
    )
    parser.add_argument("source", help=".skill file path, GitHub URL, or local directory path")
    parser.add_argument("--skills-dir", type=Path, default=DEFAULT_SKILLS_DIR,
                        help=f"Where to install skills (default: {DEFAULT_SKILLS_DIR})")
    parser.add_argument("--subdir", default=None,
                        help="Subdirectory within GitHub repo containing the skill")
    parser.add_argument("--no-update", action="store_true",
                        help="Skip running update_router.py after install")
    parser.add_argument("--skip-scan", action="store_true",
                        help="Skip pre-install security scan (not recommended)")
    parser.add_argument("--strict-scan", action="store_true",
                        help="Block install on MEDIUM findings too")
    args = parser.parse_args()

    target_dir = args.skills_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    source = args.source.strip()
    installed_path = None

    if source.startswith("https://github.com") or source.startswith("http://github.com"):
        print(f"Installing from GitHub: {source}")
        installed_path = install_github_repo(
            source, target_dir, args.subdir, args.skip_scan, args.strict_scan
        )

    elif source.endswith(".skill"):
        skill_file = Path(source).resolve()
        if not skill_file.exists():
            print(f"[error] File not found: {skill_file}")
            sys.exit(1)
        print(f"Installing .skill file: {skill_file.name}")
        installed_path = install_skill_file(
            skill_file, target_dir, args.skip_scan, args.strict_scan
        )

    else:
        local_dir = Path(source).resolve()
        if not local_dir.exists() or not local_dir.is_dir():
            print(f"[error] Not a valid path or URL: {source}")
            sys.exit(1)
        print(f"Installing from local directory: {local_dir}")
        installed_path = install_local_dir(
            local_dir, target_dir, args.skip_scan, args.strict_scan
        )

    if installed_path and not args.no_update:
        run_update(target_dir)
    elif not installed_path:
        print("Nothing installed.")
    else:
        print("Skipping router update (--no-update).")


if __name__ == "__main__":
    main()
