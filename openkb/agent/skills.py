"""Skill discovery for openkb chat — Anthropic-style SKILL.md format.

Scans skill directories and returns the metadata list the OpenAI Agents
SDK expects for ``ShellTool.environment.skills``: a list of
``{name, description, path}`` dicts.

Skill search roots (first hit wins on name collision):

  1. ``extra_roots``   — roots a CALLER passes explicitly (see
                         ``scan_local_skills``). Nothing is auto-discovered
                         here; someone has to name the directory.
  2. bundled skills    — the skills shipped with OpenKB itself
                         (``BUNDLED_SKILL_ROOTS``), lowest priority so an
                         explicit root can override a built-in.

OpenKB scans NOTHING outside its own package by default. It used to also
sweep ``<kb>/skills/``, ``~/.openkb/skills/`` and ``~/.claude/skills/``; that
last one pulled every Claude Code skill on the machine into OpenKB's chat
prompt, so a KB's answers could be steered by instructions that had nothing
to do with OpenKB or with that knowledge base. The other two were
manual-only conventions no code ever created. All three are gone: OpenKB's
skill surface is now exactly what ships in the repo, plus whatever a caller
names on purpose.

Skill file layout::

    <root>/<skill-name>/
      SKILL.md          # frontmatter + body
      references/...    # optional supporting files (the skill body can
                        # cite them; agent reads via shell)

Frontmatter::

    ---
    name: my-skill
    description: One-line trigger description the agent sees up front.
    ---
    <skill body — instructions the agent reads when it loads the skill>
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable, Tuple

import yaml

#: Auto-scanned roots outside the package. Deliberately EMPTY: OpenKB must be
#: independent of skills installed for other tools (notably ``~/.claude/skills``,
#: whose contents were being injected into every OpenKB chat prompt). Kept as a
#: named constant rather than deleted so the "what does OpenKB scan?" answer
#: stays greppable, and so a future opt-in has an obvious home.
DEFAULT_SKILL_ROOTS: Tuple[str, ...] = ()

# Skills shipped with the package so the built-in deck themes + html critic
# work out of the box (no manual install). Two candidates cover both install
# modes; whichever exists is scanned, at lowest priority:
#   - wheel install:  force-included at ``openkb/_skills/``
#   - editable/source checkout:  the repo's top-level ``skills/``
_PKG_DIR = Path(__file__).resolve().parent.parent
BUNDLED_SKILL_ROOTS: Tuple[str, ...] = (
    str(_PKG_DIR / "_skills"),
    str(_PKG_DIR.parent / "skills"),
)


def _parse_frontmatter(text: str) -> Tuple[dict, str]:
    """Return ``(metadata_dict, body)`` from a markdown file with YAML
    frontmatter delimited by ``---`` lines. Files without frontmatter
    return ``({}, full_text)``.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    try:
        end = lines.index("---", 1)
    except ValueError:
        return {}, text
    try:
        meta = yaml.safe_load("\n".join(lines[1:end])) or {}
    except yaml.YAMLError:
        meta = {}
    body = "\n".join(lines[end + 1 :])
    return meta if isinstance(meta, dict) else {}, body


def read_skill_support_file(skill_root: Path, path: str) -> str:
    """Read one supporting file without escaping the selected skill directory."""
    root = skill_root.resolve()
    target = (root / path).resolve()
    if not target.is_relative_to(root):
        return "Access denied: path escapes the skill directory."
    if not target.is_file():
        return f"File not found: {path}"
    try:
        return target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return f"Could not read {path}: {exc}"


def scan_local_skills(
    kb_dir: Path,
    extra_roots: Iterable[str | Path] = (),
) -> list[dict[str, str]]:
    """Scan known skill directories. Return SDK-shape skill list.

    Each entry is ``{"name": str, "description": str, "path": str}`` —
    the exact shape :class:`agents.ShellToolLocalSkill` expects.

    Only the package's own ``BUNDLED_SKILL_ROOTS`` are scanned automatically.
    A caller that genuinely wants another directory has to name it via
    *extra_roots* — OpenKB never goes looking for skills installed for other
    tools (see the module docstring).

    Args:
        kb_dir: KB root. Only used to resolve a RELATIVE entry in
            *extra_roots*; no root under it is scanned by default.
        extra_roots: Additional roots to scan, ahead of the bundled ones.

    Returns:
        List of skill metadata dicts. Empty if no skills found.
    """
    seen: dict[str, dict[str, str]] = {}
    # Bundled roots go last so an explicitly-passed root overrides a built-in.
    roots = list(DEFAULT_SKILL_ROOTS) + [str(r) for r in extra_roots] + list(BUNDLED_SKILL_ROOTS)
    for root_spec in roots:
        root = Path(root_spec).expanduser()
        if not root.is_absolute():
            root = kb_dir / root
        if not root.is_dir():
            continue
        for skill_dir in sorted(root.iterdir()):
            if not skill_dir.is_dir():
                continue
            md = skill_dir / "SKILL.md"
            if not md.is_file():
                continue
            try:
                text = md.read_text(encoding="utf-8")
            except OSError:
                continue
            meta, _body = _parse_frontmatter(text)
            name = str(meta.get("name") or skill_dir.name).strip()
            desc = str(meta.get("description") or "").strip()
            if not name or not desc:
                continue  # SDK requires both
            if name in seen:
                continue  # first-hit-wins; earlier roots take precedence
            seen[name] = {
                "name": name,
                "description": desc[:1024],
                "path": str(skill_dir.resolve()),
            }
    return list(seen.values())
