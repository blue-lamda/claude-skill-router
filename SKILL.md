---
name: skill-router
description: >
  Master routing skill. ALWAYS read this skill FIRST before any task that might
  involve a specialized skill — file creation, document work, writing, coding,
  presentations, spreadsheets, design, humanizing text, or any multi-step
  workflow. This skill tells you exactly which other skill to use and when.
  Use it to resolve ambiguity when multiple skills could apply. Use it when
  you're unsure if a skill exists for the task. This is the single source of
  truth for all available skills — consult it before guessing.
---

# Skill Router (Semantic)

You are Claude with access to a curated set of skills. This file is your **routing brain** — it tells you which skill to load using a two-pass semantic matching process.

---

## Routing Process

### Pass 1: Identify the Category

Read the user's message and ask: what domain does this belong to?

Match against these categories:

- **writing** — editing, rewriting, humanizing, tone, style, voice, copy
- **documents** — Word files, PDFs, spreadsheets, presentations, formal outputs
- **design** — web components, UI, HTML/CSS, React, visual layouts
- **files** — reading, extracting, or inspecting uploaded files
- **skills** — creating, improving, or managing Claude skills themselves
- **meta** — routing is unclear, or user asks if a skill exists

### Pass 2: Match Intent Within Category

Once you know the category, go to that category's section below. Read the trigger phrases for each skill. Pick the skill whose trigger phrases most closely match what the user actually said — in meaning, not just keywords.

### Confidence Check

Before loading a skill, ask yourself: am I at least 80% confident this is the right one?

- **Yes** → load it immediately
- **No** → ask one clarifying question. Example: "Do you want to rewrite this to remove AI patterns, or match a specific brand voice?" Then route based on the answer.

Never guess and silently load the wrong skill.

---

## Skill Registry

### WRITING

Skills that operate on text — changing its style, tone, voice, or quality.

---

**slop-humanizer**
Path: `/mnt/skills/user/slop-humanizer/SKILL.md`
Intent: Strip AI writing patterns. Make text sound like a specific human wrote it.
Trigger phrases:
- "this sounds too AI"
- "humanize this"
- "remove AI patterns"
- "de-slop this"
- "make this sound less robotic"
- "ChatGPT wrote this, fix it"
- "too formal, too stiff"
- "sounds generic"
Conflicts: none currently
Priority: 1

---

> No other writing skills installed yet. When you add one, run `scripts/update_router.py`.

---

### DOCUMENTS

Skills that produce or manipulate file-based documents.

Conflict rule: **output format decides.**
- User says "Word" or "document" → docx
- User says "PDF" and wants to produce/edit → pdf
- User says "PDF" and wants to read/extract → pdf-reading
- User says "spreadsheet", "table", ".csv", ".xlsx" → xlsx
- User says "deck", "slides", "presentation" → pptx

---

**docx**
Path: `/mnt/skills/public/docx/SKILL.md`
Intent: Create or edit Word documents with formatting, structure, and professional layout.
Trigger phrases:
- "create a Word doc"
- "write this as a .docx"
- "make me a report"
- "format this as a memo"
- "I need a letter"
- "create a template"
- "add a table of contents"
Conflicts: pdf (prefer docx when user says "Word" or "document")
Priority: 2

---

**pdf**
Path: `/mnt/skills/public/pdf/SKILL.md`
Intent: Create, merge, split, watermark, fill, or encrypt PDF files.
Trigger phrases:
- "create a PDF"
- "merge these PDFs"
- "split this PDF"
- "add a watermark"
- "fill this form"
- "combine PDF files"
- "encrypt this PDF"
Conflicts: pdf-reading (prefer pdf for creation/editing)
Priority: 2

---

**pdf-reading**
Path: `/mnt/skills/public/pdf-reading/SKILL.md`
Intent: Read, extract, inspect, or summarize content from an existing PDF.
Trigger phrases:
- "read this PDF"
- "extract text from"
- "what does this PDF say"
- "summarize this document"
- "pull the table from this PDF"
- "get the data out of"
Conflicts: pdf (prefer pdf-reading when goal is understanding, not producing)
Priority: 2

---

**pptx**
Path: `/mnt/skills/public/pptx/SKILL.md`
Intent: Create or edit PowerPoint presentations and slide decks.
Trigger phrases:
- "make a presentation"
- "create a deck"
- "build slides"
- "pitch deck"
- "slide for each"
- "add a slide"
- ".pptx"
Conflicts: none
Priority: 2

---

**xlsx**
Path: `/mnt/skills/public/xlsx/SKILL.md`
Intent: Create or manipulate spreadsheets, tabular data, or structured data files.
Trigger phrases:
- "create a spreadsheet"
- "make an Excel file"
- "build a table"
- ".xlsx"
- ".csv"
- "tabular format"
- "add a column"
- "clean this data"
Conflicts: none
Priority: 2

---

### FILES

Skills for handling uploaded files whose contents are not yet in context.

---

**file-reading**
Path: `/mnt/skills/public/file-reading/SKILL.md`
Intent: Router for uploaded files. Identifies file type and delegates to the right reading strategy.
Trigger phrases:
- a file path appears in context but content is NOT visible
- "/mnt/user-data/uploads/" appears
- user says "I uploaded a file"
- user refers to an attachment Claude hasn't read yet
Conflicts: pdf-reading (file-reading will redirect there automatically for PDFs)
Priority: 1 — load this before any document skill if file content is missing

---

### DESIGN

Skills for building visual or interactive web-based outputs.

---

**frontend-design**
Path: `/mnt/skills/public/frontend-design/SKILL.md`
Intent: Build web components, pages, and UI with high design quality.
Trigger phrases:
- "build a landing page"
- "create a React component"
- "design a UI"
- "make this look good"
- "HTML/CSS layout"
- "web component"
- "dashboard UI"
- "style this page"
Conflicts: none
Priority: 2

---

### SKILLS

Skills for creating and managing other Claude skills.

---

**skill-creator**
Path: `/mnt/skills/examples/skill-creator/SKILL.md`
Intent: Create, test, benchmark, improve, or package a new Claude skill.
Trigger phrases:
- "create a skill"
- "make a new skill"
- "improve this skill"
- "benchmark this skill"
- "package the skill"
- "write a SKILL.md"
- "turn this into a skill"
Conflicts: skill-router (prefer skill-creator for building new skills; skill-router for routing decisions)
Priority: 2

---

**skill-router** *(this file)*
Path: `/mnt/skills/user/skill-router/SKILL.md`
Intent: Route requests to the right skill. Meta-skill.
Trigger phrases:
- "do you have a skill for"
- "which skill should I use"
- "I'm not sure which skill"
- routing confidence is below 80%
Conflicts: none
Priority: 0 — always loaded first

---

### META (Anthropic Product Knowledge)

---

**product-self-knowledge**
Path: `/mnt/skills/public/product-self-knowledge/SKILL.md`
Intent: Answer questions about Anthropic's products accurately — models, pricing, API, Claude Code.
Trigger phrases:
- "what models does Claude have"
- "how much does the API cost"
- "how do I use Claude Code"
- "what's the difference between Sonnet and Opus"
- "Claude's rate limits"
- any response that would require stating Anthropic product facts from memory
Conflicts: none
Priority: 1 — load this any time you'd otherwise rely on memory for Anthropic product details

---

## Adding New Skills

Every skill you install should have this in its frontmatter:

```yaml
---
name: skill-name
category: writing | documents | design | files | skills | meta
description: >
  What it does and when to trigger it.
intent: one-line summary of the specific job
triggers:
  - "phrase the user might actually say"
  - "another real user phrase"
  - "and another"
conflicts: other-skill-name (optional)
priority: 1-3
---
```

Then run:
```bash
python scripts/update_router.py --skills-dir /path/to/your/skills
```

The script reads these fields and rebuilds this registry automatically.

---

## Priority Reference

- **0** — Always fires (this router)
- **1** — Fire before other skills in the same category (e.g. file-reading before docx)
- **2** — Standard priority
- **3** — Only use if no priority-1 or priority-2 skill matches

---

## Scripts (Sub-Skills)

These scripts live in `scripts/` and are part of the meta-skill. Claude knows about them and can instruct the user to run them.

---

### `install_skill.py` — Install any skill in one command

Handles `.skill` files, GitHub repos, and local directories. Always triggers `update_router.py` after a successful install.

```bash
# Install a .skill file
python scripts/install_skill.py ~/Downloads/my-skill.skill

# Install from GitHub
python scripts/install_skill.py https://github.com/user/repo

# Install from GitHub subdirectory
python scripts/install_skill.py https://github.com/user/repo --subdir skills/my-skill

# Install from a local folder
python scripts/install_skill.py ./my-skill-folder
```

Claude should tell the user to run this whenever they mention:
- "I found a new skill on GitHub"
- "I downloaded a .skill file"
- "How do I add this skill?"
- "I want to install a skill"

---

### `skill_watcher.py` — Auto-update router when skills change

A persistent background process. Watches your skills directory for new SKILL.md files (repos cloned in) or `.skill` files dropped into a folder. Fires `update_router.py` automatically with a debounce so rapid file events don't cause multiple updates.

```bash
# Start the watcher (stays running)
python scripts/skill_watcher.py --skills-dir ~/.claude/skills

# Also watch Downloads for dropped .skill files
python scripts/skill_watcher.py --skills-dir ~/.claude/skills --install-dir ~/Downloads

# Run in background
nohup python scripts/skill_watcher.py --skills-dir ~/.claude/skills &
```

Set it up as a background service so it runs automatically on login. Instructions for macOS (launchd) and Linux (systemd) are at the bottom of the script.

Claude should tell the user to run this whenever they say:
- "I don't want to run the update script manually"
- "Can this update automatically?"
- "Set it and forget it"

---

### `update_router.py` — Rebuild the Skill Registry manually

Run this any time you want to force a router rebuild without the watcher.

```bash
python scripts/update_router.py --skills-dir ~/.claude/skills
python scripts/update_router.py --dry-run   # preview without writing
```

---

## Future: Upgrading to Vector Routing

This semantic router is designed to be vector-ready. When your skill count exceeds ~50 per category and semantic matching degrades, the upgrade path is:

1. Run `scripts/embed_skills.py` (not yet built) — embeds all trigger phrases using an embedding model
2. Store vectors in a local `.faiss` or `.json` index
3. At routing time, embed the user message and do nearest-neighbor lookup
4. Pass the top 3 matches to Claude for final selection

The `category`, `intent`, and `triggers` fields in frontmatter map directly to this pipeline. No restructuring needed when you're ready to upgrade.
