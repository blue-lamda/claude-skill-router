#!/usr/bin/env python3
"""
uninstall_skill.py — Remove an installed skill and update the router.

Usage:
    python uninstall_skill.py                        # interactive picker
    python uninstall_skill.py slop-humanizer         # remove by name
    python uninstall_skill.py --list                 # list installed skills
    python uninstall_skill.py --all                  # remove ALL user skills

Options:
    --skills-dir    Where skills are installed (default: ~/.claude/skills/user)
    --no-update     Skip running update_router.py after removal
    --yes           Skip confirmation prompt
"""

import os
import sys
import shutil
import argparse
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DEFAULT_SKILLS_DIR = Path(os.path.expanduser("~/.claude/skills/user"))

# Re-use run_update from install_skill to avoid duplication
sys.path.insert(0, str(SCRIPT_DIR))
from install_skill import run_update  # noqa: E402


def list_skills(skills_dir: Path) -> list[Path]:
    """Return all skill directories (those containing a SKILL.md)."""
    if not skills_dir.exists():
        return []
    return sorted(
        d for d in skills_dir.iterdir()
        if d.is_dir() and (d / "SKILL.md").exists()
    )


def print_skills(skills: list[Path]):
    if not skills:
        print("No skills installed.")
        return
    print(f"Installed skills ({len(skills)}):")
    for s in skills:
        print(f"  - {s.name}")


def confirm(prompt: str) -> bool:
    return input(f"{prompt} [y/N] ").strip().lower() == "y"


def remove_skill(skill_dir: Path, yes: bool) -> bool:
    if not skill_dir.exists():
        print(f"[error] Skill not found: {skill_dir.name}")
        return False
    if not yes and not confirm(f"  Remove '{skill_dir.name}'?"):
        print("  Skipping.")
        return False
    shutil.rmtree(skill_dir)
    print(f"  [ok] Removed {skill_dir.name}")
    return True



def main():
    parser = argparse.ArgumentParser(description="Uninstall a Claude skill.")
    parser.add_argument("skill", nargs="?", default=None,
                        help="Name of the skill to remove (omit for interactive picker)")
    parser.add_argument("--skills-dir", type=Path, default=DEFAULT_SKILLS_DIR,
                        help=f"Skills directory (default: {DEFAULT_SKILLS_DIR})")
    parser.add_argument("--list", action="store_true",
                        help="List installed skills and exit")
    parser.add_argument("--all", action="store_true",
                        help="Remove all installed user skills")
    parser.add_argument("--no-update", action="store_true",
                        help="Skip running update_router.py after removal")
    parser.add_argument("--yes", action="store_true",
                        help="Skip confirmation prompts")
    args = parser.parse_args()

    skills_dir = args.skills_dir.resolve()
    installed = list_skills(skills_dir)

    if args.list:
        print_skills(installed)
        return

    if not installed:
        print("No skills installed.")
        return

    removed_any = False

    if args.all:
        print_skills(installed)
        print()
        if not args.yes and not confirm(f"Remove all {len(installed)} skill(s)?"):
            print("Aborted.")
            return
        for skill_dir in installed:
            if remove_skill(skill_dir, yes=True):
                removed_any = True

    elif args.skill:
        skill_dir = skills_dir / args.skill
        removed_any = remove_skill(skill_dir, yes=args.yes)

    else:
        # Interactive picker
        print_skills(installed)
        print()
        choice = input("Enter skill name to remove (or 'q' to quit): ").strip()
        if choice == "q" or not choice:
            print("Aborted.")
            return
        skill_dir = skills_dir / choice
        removed_any = remove_skill(skill_dir, yes=args.yes)

    if removed_any and not args.no_update:
        run_update(skills_dir)
    elif not removed_any:
        print("Nothing removed.")


if __name__ == "__main__":
    main()
