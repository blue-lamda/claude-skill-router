#!/usr/bin/env python3
"""
scan_skill.py — Pre-install security scanner for Claude skills.

Detects:
  - Zip Slip              directory traversal paths inside .skill zip files
  - Prompt Injection      instruction overrides / role hijacking in SKILL.md content
  - Path Traversal        dangerous characters in the skill name frontmatter field
  - Markdown Injection    control characters or newlines in trigger/intent fields
                          that could inject fake entries into the router registry
  - Sensitive Files       credentials, keys, or tokens present in the skill directory
  - Oversized SKILL.md    files large enough to cause YAML parse exhaustion

Usage:
    python scan_skill.py path/to/skill-dir        scan an extracted skill directory
    python scan_skill.py path/to/skill.skill      scan a .skill zip before extraction
    python scan_skill.py --list-patterns          show all prompt injection patterns

Options:
    --strict      Exit non-zero on MEDIUM findings too (default: only HIGH/CRITICAL)
    --json        Output findings as JSON

Exit codes:
    0   Clean (or only LOW/INFO findings)
    1   MEDIUM findings present (only fatal with --strict)
    2   HIGH or CRITICAL findings — install should be blocked
"""

import re
import sys
import json
import zipfile
import argparse
from dataclasses import dataclass, field
from pathlib import Path

# ---------------------------------------------------------------------------
# Severity levels
# ---------------------------------------------------------------------------

CRITICAL = "CRITICAL"
HIGH     = "HIGH"
MEDIUM   = "MEDIUM"
LOW      = "LOW"
INFO     = "INFO"

_SEVERITY_RANK = {CRITICAL: 4, HIGH: 3, MEDIUM: 2, LOW: 1, INFO: 0}

_ANSI = {
    CRITICAL: "\033[1;31m",  # bold red
    HIGH:     "\033[31m",    # red
    MEDIUM:   "\033[33m",    # yellow
    LOW:      "\033[36m",    # cyan
    INFO:     "\033[37m",    # white
    "RESET":  "\033[0m",
    "BOLD":   "\033[1m",
}


@dataclass
class Finding:
    severity: str
    code: str
    title: str
    detail: str
    location: str = ""
    line: int = 0

    def __str__(self):
        loc = f" [{self.location}:{self.line}]" if self.line else (f" [{self.location}]" if self.location else "")
        color = _ANSI.get(self.severity, "")
        reset = _ANSI["RESET"]
        return f"{color}[{self.severity}]{reset} {self.code}: {self.title}{loc}\n         {self.detail}"


# ---------------------------------------------------------------------------
# Prompt injection patterns
# ---------------------------------------------------------------------------

_PROMPT_INJECTION_PATTERNS = [
    (HIGH,     "PI-001", "Instruction override",
     re.compile(r"ignore\s+(all\s+)?(previous|prior|above|your)\s+(instructions?|rules?|guidelines?|prompts?)", re.I)),
    (HIGH,     "PI-002", "Instruction discard",
     re.compile(r"(disregard|forget|override|bypass|circumvent)\s+(all\s+)?(instructions?|rules?|guidelines?|constraints?)", re.I)),
    (HIGH,     "PI-003", "Role hijacking",
     re.compile(r"(you\s+are\s+now|act\s+as|pretend\s+(you\s+are|to\s+be)|your\s+(new|true|real)\s+(role|identity|persona))", re.I)),
    (HIGH,     "PI-004", "System prompt injection",
     re.compile(r"(\[SYSTEM\]|<system>|###\s*system|SYSTEM\s*:)", re.I)),
    (HIGH,     "PI-005", "Jailbreak attempt",
     re.compile(r"(developer\s+mode|unrestricted\s+mode|DAN\s+mode|jailbreak|no\s+restrictions)", re.I)),
    (HIGH,     "PI-006", "Credential/file exfiltration",
     re.compile(r"(~\/\.claude|~\/\.ssh|~\/\.env|\/etc\/passwd|id_rsa|authorized_keys)", re.I)),
    (HIGH,     "PI-007", "Self-modification attempt",
     re.compile(r"(rewrite|overwrite|modify|update|delete)\s+(the\s+)?(skill.?router|SKILL\.md|router\.md)", re.I)),
    (MEDIUM,   "PI-008", "Hidden instruction via whitespace",
     re.compile(r"(\n\s*){5,}(ignore|forget|you are|act as)", re.I)),
    (MEDIUM,   "PI-009", "Possible base64 encoded payload",
     re.compile(r"[A-Za-z0-9+/]{80,}={0,2}")),
    (MEDIUM,   "PI-010", "Unicode directional override (RTLO/LTRO)",
     re.compile(r"[\u202e\u202d\u200f\u200e\u2066\u2067\u2068\u2069\u206a-\u206f]")),
    (MEDIUM,   "PI-011", "Zero-width characters (possible steganography)",
     re.compile(r"[\u200b\u200c\u200d\ufeff\u00ad]")),
    (LOW,      "PI-012", "Suspicious privilege escalation language",
     re.compile(r"(you\s+have\s+(full\s+)?(permission|access|authority)|you\s+are\s+(authorized|allowed|permitted)\s+to)", re.I)),
    (LOW,      "PI-013", "Social engineering — credential request",
     re.compile(r"(api\s*key|password|secret|token).{0,30}(expired?|invalid|enter|provide|re.?enter)", re.I)),
]

_SENSITIVE_FILE_PATTERNS = [
    ".env", ".env.*", "*.pem", "*.key", "*.p12", "*.pfx", "*.crt",
    "id_rsa", "id_ed25519", "id_dsa", "id_ecdsa",
    "credentials", "credentials.json", "credentials.yaml",
    "secrets.json", "secrets.yaml", "secrets.toml",
    "*.token", ".netrc", ".npmrc", ".pypirc",
]

_SAFE_NAME_RE = re.compile(r'^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$')
_SAFE_IDENT_RE = re.compile(r'^[a-zA-Z0-9_.-]+$')
_CONTROL_CHAR_RE = re.compile(r'[\r\n\x00-\x1f\x7f]')

MAX_SKILL_MD_BYTES = 50 * 1024  # 50 KB


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------

def scan_zip(zip_path: Path) -> list[Finding]:
    """Scan a .skill zip file for Zip Slip and sensitive file paths."""
    findings = []
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            for name in z.namelist():
                parts = Path(name).parts
                if any(p == ".." for p in parts):
                    findings.append(Finding(
                        severity=CRITICAL, code="ZS-001",
                        title="Zip Slip: directory traversal in archive",
                        detail=f"Entry '{name}' contains '..' — could write outside install directory.",
                        location=str(zip_path),
                    ))
                if name.startswith("/"):
                    findings.append(Finding(
                        severity=CRITICAL, code="ZS-002",
                        title="Zip Slip: absolute path in archive",
                        detail=f"Entry '{name}' is an absolute path.",
                        location=str(zip_path),
                    ))
                filename = Path(name).name.lower()
                for pat in _SENSITIVE_FILE_PATTERNS:
                    if _match_pattern(filename, pat):
                        findings.append(Finding(
                            severity=MEDIUM, code="SF-001",
                            title="Sensitive file in archive",
                            detail=f"'{name}' matches sensitive file pattern '{pat}'.",
                            location=str(zip_path),
                        ))
                        break
    except zipfile.BadZipFile as e:
        findings.append(Finding(
            severity=HIGH, code="ZS-003",
            title="Invalid zip file",
            detail=str(e),
            location=str(zip_path),
        ))
    return findings


def scan_directory(skill_dir: Path) -> list[Finding]:
    """Scan an extracted skill directory."""
    findings = []

    # Check SKILL.md exists
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        findings.append(Finding(
            severity=LOW, code="SK-001",
            title="No SKILL.md found",
            detail="Directory may not be a valid skill.",
            location=str(skill_dir),
        ))
        return findings

    # File size check (YAML bomb / exhaustion)
    size = skill_md.stat().st_size
    if size > MAX_SKILL_MD_BYTES:
        findings.append(Finding(
            severity=HIGH, code="SZ-001",
            title="SKILL.md exceeds size limit",
            detail=f"File is {size // 1024}KB (limit: {MAX_SKILL_MD_BYTES // 1024}KB). "
                   "Could cause YAML parse exhaustion.",
            location="SKILL.md",
        ))

    # Read content
    try:
        content = skill_md.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        findings.append(Finding(
            severity=HIGH, code="SK-002",
            title="Cannot read SKILL.md",
            detail=str(e),
            location="SKILL.md",
        ))
        return findings

    # Skill name validation (from frontmatter)
    name = _extract_frontmatter_field(content, "name")
    if name:
        if not _SAFE_NAME_RE.match(name):
            findings.append(Finding(
                severity=HIGH, code="PT-001",
                title="Unsafe skill name — path traversal risk",
                detail=f"name: '{name}' contains characters outside [a-zA-Z0-9_-]. "
                       "This value is used as a directory name during install.",
                location="SKILL.md",
            ))

    # Frontmatter field injection (triggers, intent written into router markdown)
    for fname in ("triggers", "intent", "conflicts"):
        value = _extract_frontmatter_field(content, fname)
        if value and _CONTROL_CHAR_RE.search(value):
            findings.append(Finding(
                severity=HIGH, code="MI-001",
                title=f"Markdown injection in '{fname}' field",
                detail=f"The '{fname}' frontmatter field contains newlines or control characters "
                       "that could inject fake skill entries into the router registry.",
                location="SKILL.md",
            ))

    # Prompt injection scan on full content
    for line_num, line in enumerate(content.splitlines(), start=1):
        for severity, code, title, pattern in _PROMPT_INJECTION_PATTERNS:
            if pattern.search(line):
                findings.append(Finding(
                    severity=severity, code=code, title=title,
                    detail=f"Matched: {line.strip()[:120]}",
                    location="SKILL.md", line=line_num,
                ))

    # Sensitive files in directory
    for f in skill_dir.rglob("*"):
        if f.is_file():
            fname_lower = f.name.lower()
            for pat in _SENSITIVE_FILE_PATTERNS:
                if _match_pattern(fname_lower, pat):
                    rel = f.relative_to(skill_dir)
                    findings.append(Finding(
                        severity=MEDIUM, code="SF-001",
                        title="Sensitive file in skill directory",
                        detail=f"'{rel}' matches pattern '{pat}'. "
                               "This file would be copied to your skills directory.",
                        location=str(rel),
                    ))
                    break

    # Symlinks that point outside the skill directory
    for f in skill_dir.rglob("*"):
        if f.is_symlink():
            target = f.resolve()
            try:
                target.relative_to(skill_dir.resolve())
            except ValueError:
                rel = f.relative_to(skill_dir)
                findings.append(Finding(
                    severity=HIGH, code="SL-001",
                    title="Symlink escapes skill directory",
                    detail=f"'{rel}' → '{target}'. Could expose files outside the skill.",
                    location=str(rel),
                ))

    return findings


def scan_github_inputs(owner: str, repo: str, subdir: str | None) -> list[Finding]:
    """Validate GitHub URL components before download."""
    findings = []
    if not _SAFE_IDENT_RE.match(owner):
        findings.append(Finding(
            severity=HIGH, code="GH-001",
            title="Unsafe GitHub owner name",
            detail=f"'{owner}' contains characters that could manipulate the download URL.",
        ))
    if not _SAFE_IDENT_RE.match(repo):
        findings.append(Finding(
            severity=HIGH, code="GH-002",
            title="Unsafe GitHub repo name",
            detail=f"'{repo}' contains characters that could manipulate the download URL.",
        ))
    if subdir:
        parts = Path(subdir).parts
        if any(p == ".." for p in parts) or subdir.startswith("/"):
            findings.append(Finding(
                severity=HIGH, code="GH-003",
                title="Path traversal in --subdir",
                detail=f"'{subdir}' contains '..' or an absolute path — could navigate outside the repo.",
            ))
    return findings


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_frontmatter_field(content: str, field: str) -> str | None:
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return None
    fm = match.group(1)
    m = re.search(rf"^{re.escape(field)}\s*:\s*(.+)$", fm, re.MULTILINE)
    return m.group(1).strip() if m else None


def _match_pattern(filename: str, pattern: str) -> bool:
    """Simple glob-style match (only supports leading/trailing *)."""
    if pattern.startswith("*") and pattern.endswith("*"):
        return pattern[1:-1] in filename
    if pattern.startswith("*."):
        return filename.endswith(pattern[1:])
    if pattern.endswith("*"):
        return filename.startswith(pattern[:-1])
    return filename == pattern


def worst_severity(findings: list[Finding]) -> str:
    if not findings:
        return INFO
    return max(findings, key=lambda f: _SEVERITY_RANK[f.severity]).severity


def print_report(findings: list[Finding], skill_name: str = ""):
    label = f" for '{skill_name}'" if skill_name else ""
    bold = _ANSI["BOLD"]
    reset = _ANSI["RESET"]

    if not findings:
        print(f"{bold}Scan{label}: clean{reset}")
        return

    by_sev = {s: [] for s in [CRITICAL, HIGH, MEDIUM, LOW, INFO]}
    for f in findings:
        by_sev[f.severity].append(f)

    print(f"{bold}Scan results{label}:{reset}")
    for sev in [CRITICAL, HIGH, MEDIUM, LOW, INFO]:
        for f in by_sev[sev]:
            print(f"  {f}")
    print()

    counts = {s: len(v) for s, v in by_sev.items() if v}
    summary = ", ".join(f"{c} {s}" for s, c in counts.items())
    ws = worst_severity(findings)
    color = _ANSI.get(ws, "")
    print(f"  {color}Worst: {ws}{reset} — {summary}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Scan a Claude skill for security issues.")
    parser.add_argument("path", nargs="?", help="Path to skill directory or .skill zip file")
    parser.add_argument("--strict", action="store_true",
                        help="Exit non-zero on MEDIUM findings too")
    parser.add_argument("--json", action="store_true",
                        help="Output findings as JSON")
    parser.add_argument("--list-patterns", action="store_true",
                        help="List all prompt injection patterns and exit")
    args = parser.parse_args()

    if args.list_patterns:
        print("Prompt injection patterns:")
        for severity, code, title, pattern in _PROMPT_INJECTION_PATTERNS:
            print(f"  [{severity}] {code}: {title}")
            print(f"         regex: {pattern.pattern}")
        return

    if not args.path:
        parser.print_help()
        sys.exit(0)

    target = Path(args.path).resolve()
    if not target.exists():
        print(f"[error] Path not found: {target}")
        sys.exit(2)

    if target.suffix == ".skill":
        findings = scan_zip(target)
    elif target.is_dir():
        findings = scan_directory(target)
    else:
        print(f"[error] Expected a .skill file or directory, got: {target}")
        sys.exit(2)

    if args.json:
        print(json.dumps([
            {"severity": f.severity, "code": f.code, "title": f.title,
             "detail": f.detail, "location": f.location, "line": f.line}
            for f in findings
        ], indent=2))
    else:
        print_report(findings, target.name)

    ws = worst_severity(findings)
    if _SEVERITY_RANK[ws] >= _SEVERITY_RANK[HIGH]:
        sys.exit(2)
    if args.strict and _SEVERITY_RANK[ws] >= _SEVERITY_RANK[MEDIUM]:
        sys.exit(1)


if __name__ == "__main__":
    main()
