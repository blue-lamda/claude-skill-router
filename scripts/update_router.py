#!/usr/bin/env python3
"""
update_router.py — Rebuilds the Skill Registry in skill-router/SKILL.md
using structured frontmatter from each skill.

Reads these frontmatter fields from each SKILL.md:
  name        (required)
  category    (required: writing | documents | design | files | skills | meta)
  intent      (required: one-line job summary)
  triggers    (required: list of real user phrases)
  conflicts   (optional: comma-separated skill names)
  priority    (optional: 0-3, default 2)

Usage:
    python update_router.py
    python update_router.py --skills-dir ~/.claude/skills
    python update_router.py --skills-dir ~/.claude/skills --router-path ../SKILL.md --dry-run
"""

import os
import re
import argparse
from pathlib import Path
from collections import defaultdict
import yaml

ROUTER_SKILL_NAME = "skill-router"

CATEGORY_ORDER = ["writing", "documents", "design", "files", "skills", "meta"]

CATEGORY_LABELS = {
    "writing":   "WRITING",
    "documents": "DOCUMENTS",
    "design":    "DESIGN",
    "files":     "FILES",
    "skills":    "SKILLS",
    "meta":      "META (Anthropic Product Knowledge)",
}

CATEGORY_CONFLICT_RULES = {
    "documents": (
        "Conflict rule: **output format decides.**\n"
        "- User says \"Word\" or \"document\" → docx\n"
        "- User says \"PDF\" and wants to produce/edit → pdf\n"
        "- User says \"PDF\" and wants to read/extract → pdf-reading\n"
        "- User says \"spreadsheet\", \"table\", \".csv\", \".xlsx\" → xlsx\n"
        "- User says \"deck\", \"slides\", \"presentation\" → pptx\n"
    ),
    "files": (
        "Priority rule: **load file-reading before any document skill** "
        "if file content is missing from context.\n"
    ),
}


def parse_frontmatter(skill_md_path: Path) -> dict:
    """Extract YAML frontmatter from a SKILL.md file."""
    try:
        content = skill_md_path.read_text(encoding="utf-8")
    except Exception as e:
        print(f"  [warn] Could not read {skill_md_path}: {e}")
        return {}

    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    try:
        data = yaml.safe_load(match.group(1))
        return data if isinstance(data, dict) else {}
    except yaml.YAMLError as e:
        print(f"  [warn] YAML parse error in {skill_md_path}: {e}")
        return {}


def discover_skills(skills_dir: Path) -> list[dict]:
    """Walk skills directory and collect all structured skill metadata."""
    skills = []
    missing_fields = []

    for skill_md in sorted(skills_dir.rglob("SKILL.md")):
        if ROUTER_SKILL_NAME in str(skill_md):
            continue

        meta = parse_frontmatter(skill_md)
        name = meta.get("name")

        if not name:
            print(f"  [skip] No name in {skill_md}")
            continue

        # Determine load path
        try:
            rel = skill_md.relative_to(skills_dir.parent)
            load_path = f"/{rel}"
        except ValueError:
            load_path = str(skill_md)

        # Validate required semantic fields
        required = ["category", "intent", "triggers"]
        missing = [f for f in required if not meta.get(f)]

        if missing:
            missing_fields.append((name, missing, load_path))
            # Still include the skill, but with fallback values
            print(f"  [warn] {name} missing semantic fields: {missing} — will use description fallback")

        # Normalize triggers to a list
        triggers = meta.get("triggers", [])
        if isinstance(triggers, str):
            triggers = [t.strip() for t in triggers.split("\n") if t.strip()]

        # Fallback: derive trigger from description if no triggers field
        if not triggers:
            desc = meta.get("description", "")
            first_sentence = desc.split(".")[0].strip()
            triggers = [first_sentence] if first_sentence else ["(no triggers defined)"]

        skill = {
            "name": name,
            "load_path": load_path,
            "category": (meta.get("category") or "meta").lower().strip(),
            "intent": meta.get("intent") or meta.get("description", "")[:80],
            "triggers": triggers,
            "conflicts": meta.get("conflicts", "none"),
            "priority": int(meta.get("priority", 2)),
        }

        skills.append(skill)
        print(f"  [found] {name} ({skill['category']}, priority {skill['priority']})")

    if missing_fields:
        print(f"\n  [hint] {len(missing_fields)} skill(s) missing semantic frontmatter.")
        print("  Add 'category', 'intent', and 'triggers' to their SKILL.md for precise routing.")
        for name, fields, _ in missing_fields:
            print(f"    - {name}: missing {fields}")

    return skills


def build_registry_section(skills: list[dict]) -> str:
    """Build the full ## Skill Registry section as a markdown string."""
    by_category = defaultdict(list)
    for s in skills:
        cat = s["category"] if s["category"] in CATEGORY_ORDER else "meta"
        by_category[cat].append(s)

    # Sort within each category by priority (lower = higher priority)
    for cat in by_category:
        by_category[cat].sort(key=lambda x: x["priority"])

    lines = ["## Skill Registry"]

    for cat in CATEGORY_ORDER:
        cat_skills = by_category.get(cat, [])
        label = CATEGORY_LABELS.get(cat, cat.upper())

        lines.append(f"\n### {label}\n")

        if cat in CATEGORY_CONFLICT_RULES:
            lines.append(CATEGORY_CONFLICT_RULES[cat])

        if not cat_skills:
            lines.append(f"> No {cat} skills installed yet. When you add one, run `scripts/update_router.py`.\n")
            continue

        for s in cat_skills:
            lines.append("---\n")
            lines.append(f"**{s['name']}**")
            lines.append(f"Path: `{s['load_path']}`")
            lines.append(f"Intent: {s['intent']}")
            lines.append("Trigger phrases:")
            for t in s["triggers"]:
                lines.append(f'- "{t}"')
            lines.append(f"Conflicts: {s['conflicts']}")
            lines.append(f"Priority: {s['priority']}\n")

    # Always append the router self-reference
    lines.append("---\n")
    lines.append("**skill-router** *(this file)*")
    lines.append("Path: `/mnt/skills/user/skill-router/SKILL.md`")
    lines.append("Intent: Route requests to the right skill. Meta-skill.")
    lines.append("Trigger phrases:")
    lines.append('- "do you have a skill for"')
    lines.append('- "which skill should I use"')
    lines.append('- "I\'m not sure which skill"')
    lines.append("- routing confidence is below 80%")
    lines.append("Conflicts: none")
    lines.append("Priority: 0 — always loaded first\n")

    return "\n".join(lines)


def update_router(router_path: Path, new_registry: str, dry_run: bool = False) -> bool:
    """Replace the Skill Registry section in the router SKILL.md."""
    content = router_path.read_text(encoding="utf-8")

    pattern = r"(## Skill Registry\n)(.*?)(\n---\n\n## Adding New Skills)"
    match = re.search(pattern, content, flags=re.DOTALL)
    if not match:
        print("[error] Could not find '## Skill Registry' ... '## Adding New Skills' in router.")
        print("  Make sure SKILL.md contains these exact section headers.")
        return False

    new_content = content[:match.start()] + new_registry + "\n\n---\n\n## Adding New Skills" + content[match.end():]

    if dry_run:
        print("\n[dry-run] Would write the following registry:\n")
        print(new_registry)
        return True

    router_path.write_text(new_content, encoding="utf-8")
    return True


def print_summary(skills: list[dict]):
    by_cat = defaultdict(list)
    for s in skills:
        by_cat[s["category"]].append(s["name"])

    print("\nSkill inventory:")
    for cat in CATEGORY_ORDER:
        names = by_cat.get(cat, [])
        if names:
            print(f"  {cat}: {', '.join(names)}")
    print(f"\nTotal: {len(skills)} skill(s) across {len(by_cat)} categories.")


def main():
    parser = argparse.ArgumentParser(description="Rebuild skill-router Skill Registry from skill frontmatter.")
    parser.add_argument("--skills-dir", type=Path, default=Path(os.path.expanduser("~/.claude/skills")),
                        help="Root directory containing your skills")
    parser.add_argument("--router-path", type=Path,
                        default=Path(__file__).parent.parent / "SKILL.md",
                        help="Path to skill-router/SKILL.md")
    parser.add_argument("--dry-run", action="store_true",
                        help="Preview changes without writing to disk")
    args = parser.parse_args()

    router_path = args.router_path.resolve()
    skills_dir = args.skills_dir.resolve()

    print(f"Scanning: {skills_dir}")
    print(f"Router:   {router_path}")
    if args.dry_run:
        print("Mode:     DRY RUN (no files will be written)\n")
    print()

    if not skills_dir.exists():
        print(f"[error] Skills directory not found: {skills_dir}")
        return

    skills = discover_skills(skills_dir)
    print_summary(skills)

    new_registry = build_registry_section(skills)

    print()
    if update_router(router_path, new_registry, dry_run=args.dry_run):
        if not args.dry_run:
            print(f"[ok] Router updated at {router_path}")
    else:
        print("[fail] Router update failed.")


if __name__ == "__main__":
    main()
