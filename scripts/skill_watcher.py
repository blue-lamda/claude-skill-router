#!/usr/bin/env python3
"""
skill_watcher.py — Watches your skills directory for new or changed skills
and automatically runs update_router.py to keep skill-router in sync.

Supports both:
  - New .skill files dropped into a watched folder
  - New repos cloned into the skills directory

Usage:
    python skill_watcher.py                          # uses default paths
    python skill_watcher.py --skills-dir ~/.claude/skills
    python skill_watcher.py --install-dir ~/Downloads  # watches for .skill drops too

Run once in the background:
    nohup python skill_watcher.py &
    
Or set it up as a launchd/systemd service (see instructions at bottom of file).

Dependencies:
    pip install watchdog
"""

import os
import sys
import time
import zipfile
import logging
import argparse
import threading
import subprocess
from pathlib import Path

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    print("[error] watchdog not installed.")
    print("  Run: pip install watchdog")
    sys.exit(1)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [skill-watcher] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

SCRIPT_DIR = Path(__file__).parent
UPDATE_SCRIPT = SCRIPT_DIR / "update_router.py"
ROUTER_SKILL = SCRIPT_DIR.parent / "SKILL.md"

# Debounce: wait this many seconds after last change before firing update
# Prevents multiple rapid fires when cloning a repo (many files land at once)
DEBOUNCE_SECONDS = 3.0


class SkillChangeHandler(FileSystemEventHandler):
    def __init__(self, skills_dir: Path, install_dir: Path | None, debounce: float):
        self.skills_dir = skills_dir
        self.install_dir = install_dir
        self.debounce = debounce
        self._last_event_time = 0
        self._pending = False

    def _should_react(self, path: str) -> bool:
        p = Path(path)
        # React to new SKILL.md files (new skill cloned/added)
        if p.name == "SKILL.md":
            return True
        # React to .skill files dropped into install dir
        if p.suffix == ".skill":
            return True
        return False

    def on_created(self, event):
        if not event.is_directory and self._should_react(event.src_path):
            log.info("New file detected: %s", event.src_path)
            self._schedule_update(event.src_path)

    def on_modified(self, event):
        if not event.is_directory and self._should_react(event.src_path):
            # Only react to SKILL.md modifications, not .skill drops (they don't get modified)
            if Path(event.src_path).name == "SKILL.md":
                log.info("Skill modified: %s", event.src_path)
                self._schedule_update(event.src_path)

    def _schedule_update(self, trigger_path: str):
        self._last_event_time = time.time()
        if not self._pending:
            self._pending = True
            threading.Thread(target=self._debounced_update, args=(trigger_path,), daemon=True).start()

    def _debounced_update(self, trigger_path: str):
        """Wait for debounce window to close, then fire the update."""
        while True:
            time.sleep(0.5)
            elapsed = time.time() - self._last_event_time
            if elapsed >= self.debounce:
                break

        self._pending = False

        # If it's a .skill file, install it first
        p = Path(trigger_path)
        if p.suffix == ".skill" and self.install_dir and p.parent == self.install_dir:
            log.info("Auto-installing .skill file: %s", p.name)
            self._install_skill_file(p)

        # Then always run the router update
        self._run_update()

    def _install_skill_file(self, skill_file: Path):
        """Unzip a .skill file into the skills directory."""
        skill_name = skill_file.stem
        target_dir = self.skills_dir / "user" / skill_name
        target_dir.mkdir(parents=True, exist_ok=True)

        try:
            with zipfile.ZipFile(skill_file, "r") as z:
                # Strip top-level folder if present
                members = z.namelist()
                prefix = members[0] if members[0].endswith("/") else ""
                for member in members:
                    stripped = member[len(prefix):] if prefix else member
                    if not stripped:
                        continue
                    dest = target_dir / stripped
                    if member.endswith("/"):
                        dest.mkdir(parents=True, exist_ok=True)
                    else:
                        dest.parent.mkdir(parents=True, exist_ok=True)
                        with z.open(member) as src, open(dest, "wb") as dst:
                            dst.write(src.read())
            log.info("Installed %s to %s", skill_name, target_dir)
        except (OSError, zipfile.BadZipFile) as e:
            log.error("Failed to install %s: %s", skill_file, e)

    def _run_update(self):
        """Fire update_router.py."""
        cmd = [
            sys.executable,
            str(UPDATE_SCRIPT),
            "--skills-dir", str(self.skills_dir),
            "--router-path", str(ROUTER_SKILL),
        ]
        log.info("Running update_router.py...")
        try:
            result = subprocess.run(cmd, check=False, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                log.info("Router updated successfully.")
            else:
                log.error("update_router.py failed:\n%s", result.stderr)
        except subprocess.TimeoutExpired:
            log.error("update_router.py timed out.")
        except OSError as e:
            log.error("Failed to run update_router.py: %s", e)


def main():
    parser = argparse.ArgumentParser(description="Watch skills directory and auto-update router.")
    parser.add_argument("--skills-dir", type=Path,
                        default=Path(os.path.expanduser("~/.claude/skills")),
                        help="Root skills directory to watch")
    parser.add_argument("--install-dir", type=Path,
                        default=None,
                        help="Also watch this folder for dropped .skill files (e.g. ~/Downloads)")
    parser.add_argument("--debounce", type=float, default=DEBOUNCE_SECONDS,
                        help=f"Seconds to wait after last change before updating (default: {DEBOUNCE_SECONDS})")
    args = parser.parse_args()

    skills_dir = args.skills_dir.resolve()
    install_dir = args.install_dir.resolve() if args.install_dir else None

    if not skills_dir.exists():
        log.error("Skills directory not found: %s", skills_dir)
        log.error("Create it or pass --skills-dir /correct/path")
        sys.exit(1)

    handler = SkillChangeHandler(skills_dir, install_dir, args.debounce)
    observer = Observer()
    observer.schedule(handler, str(skills_dir), recursive=True)
    log.info("Watching skills: %s", skills_dir)

    if install_dir:
        if install_dir.exists():
            observer.schedule(handler, str(install_dir), recursive=False)
            log.info("Watching installs: %s", install_dir)
        else:
            log.warning("Install dir not found, skipping: %s", install_dir)

    observer.start()
    log.info("Skill watcher running. Press Ctrl+C to stop.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        log.info("Stopping watcher...")
        observer.stop()
    observer.join()
    log.info("Watcher stopped.")


if __name__ == "__main__":
    main()


# ============================================================
# RUNNING AS A BACKGROUND SERVICE
# ============================================================
#
# macOS (launchd):
#   1. Create ~/Library/LaunchAgents/com.claude.skill-watcher.plist:
#
#      <?xml version="1.0" encoding="UTF-8"?>
#      <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" ...>
#      <plist version="1.0">
#      <dict>
#        <key>Label</key>
#        <string>com.claude.skill-watcher</string>
#        <key>ProgramArguments</key>
#        <array>
#          <string>/usr/bin/python3</string>
#          <string>/path/to/skill-router/scripts/skill_watcher.py</string>
#          <string>--skills-dir</string>
#          <string>/path/to/your/skills</string>
#          <string>--install-dir</string>
#          <string>/Users/YOU/Downloads</string>
#        </array>
#        <key>RunAtLoad</key>
#        <true/>
#        <key>KeepAlive</key>
#        <true/>
#      </dict>
#      </plist>
#
#   2. launchctl load ~/Library/LaunchAgents/com.claude.skill-watcher.plist
#
# Linux (systemd):
#   Create /etc/systemd/system/skill-watcher.service and run:
#   systemctl enable --now skill-watcher
