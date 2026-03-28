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
DEFAULT_SKILLS_DIR = Path(os.path.expanduser("~/.claude/skills/user"))


def install_skill_file(skill_file: Path, target_dir: Path) -> Path:
    """Unzip a .skill file into target_dir/skill_name/."""
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
        # Detect and strip top-level folder
        prefix = ""
        if members and members[0].endswith("/"):
            prefix = members[0]

        for member in members:
            stripped = member[len(prefix):] if prefix else member
            if not stripped:
                continue
            out_path = dest / stripped
            if member.endswith("/"):
                out_path.mkdir(parents=True, exist_ok=True)
            else:
                out_path.parent.mkdir(parents=True, exist_ok=True)
                with z.open(member) as src, open(out_path, "wb") as dst:
                    dst.write(src.read())

    print(f"  [ok] Installed {skill_name} to {dest}")
    return dest


def install_github_repo(repo_url: str, target_dir: Path, subdir: str | None) -> Path:
    """Clone a GitHub repo and install the skill from it."""
    parsed = urlparse(repo_url)
    if parsed.scheme != "https" or parsed.netloc not in ("github.com", "www.github.com"):
        print(f"[error] Only https://github.com URLs are supported: {repo_url}")
        sys.exit(1)

    path_parts = parsed.path.strip("/").split("/")
    if len(path_parts) < 2:
        print(f"[error] Invalid GitHub URL: {repo_url}")
        sys.exit(1)

    owner, repo = path_parts[0], path_parts[1].replace(".git", "")
    zip_url = f"https://github.com/{owner}/{repo}/archive/refs/heads/main.zip"

    print(f"  Downloading {owner}/{repo}...")

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / f"{repo}.zip"

        try:
            urlretrieve(zip_url, zip_path)  # nosec B310 — URL validated as https://github.com above
        except URLError:
            # Try 'master' branch if 'main' fails
            zip_url = zip_url.replace("/main.zip", "/master.zip")
            try:
                urlretrieve(zip_url, zip_path)  # nosec B310
            except URLError as e:
                print(f"[error] Could not download repo: {e}")
                sys.exit(1)

        # Extract zip
        extract_dir = Path(tmp) / "extracted"
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(extract_dir)

        # Find root of extracted content (usually repo-main/ or repo-master/)
        extracted_roots = list(extract_dir.iterdir())
        if not extracted_roots:
            print("[error] Empty archive.")
            sys.exit(1)
        repo_root = extracted_roots[0]

        # Navigate to subdir if specified
        skill_source = repo_root / subdir if subdir else repo_root

        if not skill_source.exists():
            print(f"[error] Subdir not found in repo: {subdir}")
            sys.exit(1)

        # Check if this looks like a skill (has SKILL.md)
        if not (skill_source / "SKILL.md").exists():
            print(f"[warn] No SKILL.md found in {skill_source}")
            print("  This may not be a valid skill directory.")
            answer = input("  Continue anyway? [y/N] ").strip().lower()
            if answer != "y":
                sys.exit(0)

        # Determine skill name from SKILL.md frontmatter or directory name
        skill_name = _get_skill_name(skill_source) or repo
        dest = target_dir / skill_name

        if dest.exists():
            print(f"  [warn] {skill_name} already exists at {dest}")
            answer = input("  Overwrite? [y/N] ").strip().lower()
            if answer != "y":
                print("  Skipping install.")
                return None
            shutil.rmtree(dest)

        shutil.copytree(skill_source, dest)
        print(f"  [ok] Installed {skill_name} to {dest}")
        return dest


def install_local_dir(source: Path, target_dir: Path) -> Path:
    """Install a skill from a local directory."""
    if not (source / "SKILL.md").exists():
        print(f"[warn] No SKILL.md found in {source}")

    skill_name = _get_skill_name(source) or source.name
    dest = target_dir / skill_name

    if dest.exists():
        print(f"  [warn] {skill_name} already exists at {dest}")
        answer = input("  Overwrite? [y/N] ").strip().lower()
        if answer != "y":
            return None
        shutil.rmtree(dest)

    shutil.copytree(source, dest)
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
    # Walk up from user/ to find the root skills dir
    root_skills_dir = skills_dir.parent if skills_dir.name == "user" else skills_dir

    cmd = [
        sys.executable,
        str(UPDATE_SCRIPT),
        "--skills-dir", str(root_skills_dir),
        "--router-path", str(ROUTER_SKILL),
    ]
    print("\nUpdating skill router...")
    try:
        result = subprocess.run(cmd, check=False, timeout=30)
        if result.returncode == 0:
            print("[ok] Router updated.")
        else:
            print("[warn] Router update finished with errors. Check output above.")
    except subprocess.TimeoutExpired:
        print("[warn] Router update timed out.")
    except OSError as e:
        print(f"[warn] Could not run update_router.py: {e}")


def main():
    parser = argparse.ArgumentParser(description="Install a Claude skill from a file, GitHub repo, or local dir.")
    parser.add_argument("source", help=".skill file path, GitHub URL, or local directory path")
    parser.add_argument("--skills-dir", type=Path, default=DEFAULT_SKILLS_DIR,
                        help=f"Where to install skills (default: {DEFAULT_SKILLS_DIR})")
    parser.add_argument("--subdir", default=None,
                        help="Subdirectory within GitHub repo containing the skill")
    parser.add_argument("--no-update", action="store_true",
                        help="Skip running update_router.py after install")
    args = parser.parse_args()

    target_dir = args.skills_dir.resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    source = args.source.strip()
    installed_path = None

    if source.startswith("https://github.com") or source.startswith("http://github.com"):
        print(f"Installing from GitHub: {source}")
        installed_path = install_github_repo(source, target_dir, args.subdir)

    elif source.endswith(".skill"):
        skill_file = Path(source).resolve()
        if not skill_file.exists():
            print(f"[error] File not found: {skill_file}")
            sys.exit(1)
        print(f"Installing .skill file: {skill_file.name}")
        installed_path = install_skill_file(skill_file, target_dir)

    else:
        local_dir = Path(source).resolve()
        if not local_dir.exists() or not local_dir.is_dir():
            print(f"[error] Not a valid path or URL: {source}")
            sys.exit(1)
        print(f"Installing from local directory: {local_dir}")
        installed_path = install_local_dir(local_dir, target_dir)

    if installed_path and not args.no_update:
        run_update(target_dir)
    elif not installed_path:
        print("Nothing installed.")
    else:
        print("Skipping router update (--no-update).")


if __name__ == "__main__":
    main()
