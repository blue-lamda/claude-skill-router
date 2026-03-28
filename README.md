# claude-skill-router

A meta-skill for Claude that automatically routes requests to the right skill — no matter how many skills you have installed.

Built for people who use Claude skills heavily and don't want to manage a growing list manually.

---

## The Problem

Claude skills are powerful, but they don't scale well on their own. As your library grows:

- Claude has to scan an increasingly long list to decide which skill applies
- Overlapping skill descriptions cause wrong-skill fires
- You have to manually remember which skill does what
- There's no quality control when you install from different GitHub repos

At 10 skills it's fine. At 50 it gets messy. At 500 it breaks.

---

## What This Does

`claude-skill-router` is a single meta-skill that sits on top of all your other skills. Instead of Claude guessing from a flat list, it uses a two-pass semantic routing process:

**Pass 1** — Narrow to a category (writing, documents, design, files, skills, meta)

**Pass 2** — Within that category, match intent using real trigger phrases declared by each skill

**Confidence check** — If Claude isn't 80% sure, it asks one clarifying question instead of guessing

The router also keeps itself up to date automatically via a file watcher that runs in the background.

---

## What's Inside

```
claude-skill-router/
├── SKILL.md                    # The meta-skill itself
└── scripts/
    ├── install_skill.py        # One-command skill installer
    ├── skill_watcher.py        # Background auto-updater
    └── update_router.py        # Rebuilds the router registry
```

### `install_skill.py`
Install any skill from a `.skill` file, GitHub URL, or local folder. Always triggers a router update after install.

```bash
python scripts/install_skill.py ~/Downloads/my-skill.skill
python scripts/install_skill.py https://github.com/user/repo
python scripts/install_skill.py ./my-local-skill
```

### `skill_watcher.py`
Persistent background watcher. Detects new skills the moment they land and updates the router automatically. Supports debouncing so cloning a repo (many files at once) only triggers one update.

```bash
# Watch your skills directory
python scripts/skill_watcher.py --skills-dir ~/.claude/skills

# Also watch Downloads for dropped .skill files
python scripts/skill_watcher.py --skills-dir ~/.claude/skills --install-dir ~/Downloads

# Run in background
nohup python scripts/skill_watcher.py --skills-dir ~/.claude/skills &
```

### `update_router.py`
Manually rebuild the router registry at any time.

```bash
python scripts/update_router.py --skills-dir ~/.claude/skills
python scripts/update_router.py --dry-run    # preview without writing
```

---

## Setup

### 1. Install dependencies

```bash
pip install watchdog pyyaml
```

### 2. Install the skill

Drop `SKILL.md` into your Claude skills directory:

```bash
cp SKILL.md ~/.claude/skills/user/skill-router/SKILL.md
```

Or install the whole folder:

```bash
cp -r . ~/.claude/skills/user/skill-router/
```

### 3. Start the watcher (optional but recommended)

```bash
nohup python scripts/skill_watcher.py \
  --skills-dir ~/.claude/skills \
  --install-dir ~/Downloads &
```

After this, every new skill you install updates the router automatically.

### 4. Run macOS as a background service (optional)

Create `~/Library/LaunchAgents/com.claude.skill-watcher.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>com.claude.skill-watcher</string>
  <key>ProgramArguments</key>
  <array>
    <string>/usr/bin/python3</string>
    <string>/path/to/skill-router/scripts/skill_watcher.py</string>
    <string>--skills-dir</string>
    <string>/Users/YOU/.claude/skills</string>
    <string>--install-dir</string>
    <string>/Users/YOU/Downloads</string>
  </array>
  <key>RunAtLoad</key>
  <true/>
  <key>KeepAlive</key>
  <true/>
</dict>
</plist>
```

Then:
```bash
launchctl load ~/Library/LaunchAgents/com.claude.skill-watcher.plist
```

---

## Making Your Skills Router-Compatible

For precise routing, add these fields to your skill's frontmatter:

```yaml
---
name: my-skill
category: writing         # writing | documents | design | files | skills | meta
intent: one-line summary of what this skill does
triggers:
  - "phrase the user might actually say"
  - "another real user phrase"
  - "and another"
conflicts: other-skill-name   # optional
priority: 2                   # 1=high, 2=standard, 3=fallback
---
```

The `triggers` field is the key. Write them as real phrases someone would type, not abstract descriptions. The router matches on meaning, not keywords.

---

## Roadmap

- [ ] Vector routing upgrade path (embeddings + FAISS) for 50+ skills per category
- [ ] `embed_skills.py` — pre-compute trigger phrase embeddings
- [ ] Skill conflict detector — flags overlapping trigger phrases before they cause issues
- [ ] Web UI for browsing and managing installed skills

---

## Contributing

If you build a skill that uses this router's frontmatter format, open a PR to add it to the compatible skills list. The goal is a shared ecosystem where anyone can install from this repo and have routing just work.

---

## License

MIT
