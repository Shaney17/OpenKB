"""Direct unit tests for :mod:`openkb.agent.skills`.

Tests the scanner that ``run_skill`` / ``build_chat_agent`` depend on
to discover ``SKILL.md`` packages across multiple root directories.
Pre-existing tests only exercised the scanner indirectly (via a
test_deck_prompt assertion that the built-in deck skill loads), so
edge-case behavior (precedence, malformed frontmatter, missing fields,
description truncation) was silently uncovered.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from openkb.agent.skills import (
    DEFAULT_SKILL_ROOTS,
    _parse_frontmatter,
    read_skill_support_file,
    scan_local_skills,
)


@pytest.fixture(autouse=True)
def _isolate_home(monkeypatch, tmp_path):
    """Point ``$HOME`` at the test's tmp_path and blank the bundled roots.

    The scanner no longer reads anything under ``$HOME``, so this is now a
    belt-and-braces guard: if a home-based root is ever reintroduced, these
    unit tests must not silently start picking up the developer's real
    installed skills. Bundled roots are neutralized so the tests exercise the
    scanning primitive in isolation; bundled discovery is covered explicitly.
    """
    fake_home = tmp_path / "isolated-home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))
    monkeypatch.setattr("openkb.agent.skills.BUNDLED_SKILL_ROOTS", ())


def _scan(kb_dir: Path, root: Path):
    """Scan one explicit root — the only way a non-bundled dir is ever read."""
    return scan_local_skills(kb_dir, extra_roots=(str(root),))


def _write_skill(
    root: Path,
    name: str,
    *,
    description: str = "A test skill.",
    body: str = "instructions",
) -> Path:
    """Drop a minimally well-formed SKILL.md and return its directory."""
    sk_dir = root / name
    sk_dir.mkdir(parents=True, exist_ok=True)
    (sk_dir / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n{body}",
        encoding="utf-8",
    )
    return sk_dir


# ─── scan_local_skills ──────────────────────────────────────────────────


def test_scan_returns_empty_when_no_skill_roots_exist(tmp_path: Path):
    assert scan_local_skills(tmp_path) == []


def test_scan_finds_skills_in_an_explicit_root(tmp_path: Path):
    _write_skill(tmp_path / "skills", "alpha")
    _write_skill(tmp_path / "skills", "beta")
    skills = _scan(tmp_path, tmp_path / "skills")
    names = {s["name"] for s in skills}
    assert names == {"alpha", "beta"}


def test_scan_returns_sdk_shape(tmp_path: Path):
    """SDK contract: each entry has 'name', 'description', 'path' keys
    of type str. ``path`` is absolute (resolved)."""
    sk_dir = _write_skill(tmp_path / "skills", "shape-check")
    skills = _scan(tmp_path, tmp_path / "skills")
    assert len(skills) == 1
    s = skills[0]
    assert set(s.keys()) == {"name", "description", "path"}
    assert all(isinstance(s[k], str) for k in s)
    assert Path(s["path"]).is_absolute()
    assert Path(s["path"]) == sk_dir.resolve()


def test_scan_skips_dirs_without_skill_md(tmp_path: Path):
    """A subdirectory under skills/ that doesn't have SKILL.md is ignored,
    not an error."""
    (tmp_path / "skills" / "no-skill-here").mkdir(parents=True)
    (tmp_path / "skills" / "no-skill-here" / "README.md").write_text("nope")
    _write_skill(tmp_path / "skills", "real-skill")
    skills = _scan(tmp_path, tmp_path / "skills")
    assert [s["name"] for s in skills] == ["real-skill"]


def test_scan_skips_skill_without_description(tmp_path: Path):
    """SDK requires both name and description; missing description ->
    silently skipped (don't crash, don't include)."""
    sk_dir = tmp_path / "skills" / "no-desc"
    sk_dir.mkdir(parents=True)
    (sk_dir / "SKILL.md").write_text("---\nname: no-desc\n---\nbody")
    # And one well-formed one for control
    _write_skill(tmp_path / "skills", "well-formed")
    skills = _scan(tmp_path, tmp_path / "skills")
    assert [s["name"] for s in skills] == ["well-formed"]


def test_scan_falls_back_to_dir_name_when_frontmatter_omits_name(tmp_path: Path):
    """If frontmatter has ``description`` but no ``name``, the scanner
    uses the directory name as a sane default. This lets a user drop a
    skill directory without writing the name twice."""
    sk_dir = tmp_path / "skills" / "dir-name-only"
    sk_dir.mkdir(parents=True)
    (sk_dir / "SKILL.md").write_text("---\ndescription: x\n---\nbody")
    skills = _scan(tmp_path, tmp_path / "skills")
    assert [s["name"] for s in skills] == ["dir-name-only"]


def test_scan_truncates_long_description_to_1024(tmp_path: Path):
    """The SDK ``ShellToolLocalSkill`` description field has a length
    cap. Ours conservatively truncates at 1024 chars so any agent UI
    that surfaces this string can't be overrun."""
    long_desc = "a" * 5000
    _write_skill(tmp_path / "skills", "verbose", description=long_desc)
    skills = _scan(tmp_path, tmp_path / "skills")
    assert len(skills) == 1
    assert len(skills[0]["description"]) == 1024


def test_scan_first_hit_wins_across_roots(tmp_path: Path):
    """When the same skill name lives in multiple roots, the EARLIER root
    wins — the precedence that lets an explicit root override a built-in."""
    first = tmp_path / "first"
    second = tmp_path / "second"
    _write_skill(first, "dup", description="FIRST version")
    _write_skill(second, "dup", description="SECOND version")

    skills = scan_local_skills(tmp_path, extra_roots=(str(first), str(second)))
    dup = next(s for s in skills if s["name"] == "dup")
    assert dup["description"] == "FIRST version"


def test_scan_extra_roots_are_the_only_non_bundled_source(tmp_path: Path):
    """A caller-named root is read; the same directory is invisible without
    that explicit opt-in."""
    extra = tmp_path / "extra"
    _write_skill(extra, "extra-only")
    assert "extra-only" in {s["name"] for s in _scan(tmp_path, extra)}
    assert scan_local_skills(tmp_path) == []


# ─── isolation from other tools' skills ─────────────────────────────────


def test_no_roots_are_auto_scanned(tmp_path: Path):
    """OpenKB must scan NOTHING outside its own package by default.

    Regression guard for the "universal skill loader": it swept
    ``~/.claude/skills`` and injected every Claude Code skill's
    name+description into OpenKB's chat prompt, so a knowledge base's
    answers could be steered by instructions belonging to another tool.
    """
    assert DEFAULT_SKILL_ROOTS == ()


@pytest.mark.parametrize("root", ["skills", ".openkb/skills", ".claude/skills"])
def test_previously_swept_roots_are_ignored(tmp_path: Path, monkeypatch, root: Path):
    """The three roots the scanner used to sweep must stay invisible.

    Covers both the home-relative pair (resolved from ``$HOME``, pointed at
    the sandbox by the autouse fixture) and the KB-relative ``skills/``.
    """
    home = Path(tmp_path / "isolated-home")
    for base in (tmp_path, home):
        _write_skill(base / root, "leaked-skill", description="must not be loaded")
    assert scan_local_skills(tmp_path) == []


def test_scan_includes_bundled_skills(tmp_path: Path, monkeypatch):
    """Skills shipped with the package (deck themes / critic) are still
    discovered — this is what makes ``deck new`` work right after install,
    and after this change it is the ONLY automatic source."""
    bundled = tmp_path / "bundled"
    _write_skill(bundled, "openkb-deck-neon", description="built-in deck theme")
    monkeypatch.setattr("openkb.agent.skills.BUNDLED_SKILL_ROOTS", (str(bundled),))
    names = {s["name"] for s in scan_local_skills(tmp_path)}
    assert "openkb-deck-neon" in names


def test_explicit_root_overrides_bundled(tmp_path: Path, monkeypatch):
    """Bundled roots are scanned last (lowest priority), so a caller that
    names its own root can still customize a built-in theme."""
    bundled = tmp_path / "bundled"
    _write_skill(bundled, "openkb-deck-neon", description="BUILT-IN")
    monkeypatch.setattr("openkb.agent.skills.BUNDLED_SKILL_ROOTS", (str(bundled),))
    override = tmp_path / "override"
    _write_skill(override, "openkb-deck-neon", description="EXPLICIT OVERRIDE")
    match = next(s for s in _scan(tmp_path, override) if s["name"] == "openkb-deck-neon")
    assert match["description"] == "EXPLICIT OVERRIDE"


# ─── _parse_frontmatter ──────────────────────────────────────────────────


def test_parse_frontmatter_happy_path():
    text = "---\nname: foo\ndescription: bar\n---\nbody text"
    meta, body = _parse_frontmatter(text)
    assert meta == {"name": "foo", "description": "bar"}
    assert body == "body text"


def test_parse_frontmatter_returns_empty_when_no_delim():
    """No leading ``---`` means no frontmatter; return ({}, full_text)."""
    text = "just a body, no frontmatter"
    meta, body = _parse_frontmatter(text)
    assert meta == {}
    assert body == text


def test_parse_frontmatter_returns_empty_when_unclosed():
    """Frontmatter that opens with ``---`` but never closes is malformed;
    treat as no frontmatter rather than raising."""
    text = "---\nname: foo\nbut no closing"
    meta, body = _parse_frontmatter(text)
    assert meta == {}
    assert body == text  # everything passed through as body


def test_parse_frontmatter_handles_malformed_yaml():
    """Malformed YAML inside the delimiters shouldn't crash; return
    ({}, body). Caller is responsible for asserting required keys."""
    text = "---\n: : :\nname: foo\n---\nbody"
    meta, body = _parse_frontmatter(text)
    assert meta == {}
    assert body == "body"


def test_parse_frontmatter_non_dict_yaml_returns_empty():
    """If the frontmatter parses but isn't a dict (e.g. a YAML list),
    treat as empty metadata rather than trying to use it."""
    text = "---\n- item-1\n- item-2\n---\nbody"
    meta, body = _parse_frontmatter(text)
    assert meta == {}
    # body is correctly extracted even though metadata was discarded
    assert body == "body"


def test_parse_frontmatter_preserves_body_with_dashes():
    """Body containing standalone ``---`` (a Markdown horizontal rule) is
    preserved intact — only the FIRST closing ``---`` ends frontmatter."""
    text = "---\nname: foo\ndescription: bar\n---\nIntro\n\n---\n\nMore body"
    meta, body = _parse_frontmatter(text)
    assert meta == {"name": "foo", "description": "bar"}
    assert body == "Intro\n\n---\n\nMore body"


# ─── read_skill_file ────────────────────────────────────────────────────


def test_read_skill_support_file_is_scoped_to_selected_skill(tmp_path: Path):
    skill = _write_skill(tmp_path / "skills", "demo")
    reference = skill / "references" / "guide.md"
    reference.parent.mkdir()
    reference.write_text("GUIDE", encoding="utf-8")
    assert read_skill_support_file(skill, "references/guide.md") == "GUIDE"
    assert read_skill_support_file(skill, "../other/SKILL.md").startswith("Access denied:")
    assert read_skill_support_file(skill, "references/missing.md").startswith("File not found:")


def _skill_file_tool(kb_dir: Path):
    from openkb.agent.query import build_chat_agent

    agent = build_chat_agent(kb_dir, "gpt-4o-mini")
    return next(t for t in agent.tools if t.name == "read_skill_file")


def _ctx():
    from agents.tool_context import ToolContext

    return ToolContext(context=None, tool_name="t", tool_call_id="c", tool_arguments="{}")


@pytest.fixture
def _bundled_skill(tmp_path, monkeypatch):
    """A bundled skill with a references/ tree, like the real ask-pm."""
    bundled = tmp_path / "bundled"
    sk = _write_skill(bundled, "demo")
    (sk / "references" / "lanes").mkdir(parents=True)
    (sk / "references" / "guide.md").write_text("GUIDE BODY", encoding="utf-8")
    (sk / "references" / "lanes" / "01.md").write_text("LANE BODY", encoding="utf-8")
    monkeypatch.setattr("openkb.agent.skills.BUNDLED_SKILL_ROOTS", (str(bundled),))
    kb = tmp_path / "kb"
    (kb / "wiki").mkdir(parents=True)
    (kb / ".openkb").mkdir()
    return kb


@pytest.mark.asyncio
async def test_read_skill_file_reads_a_nested_reference(_bundled_skill):
    """Progressive-disclosure skills put their playbooks under references/;
    without this tool only SKILL.md was reachable and the rest was dead weight."""
    import json

    tool = _skill_file_tool(_bundled_skill)
    out = await tool.on_invoke_tool(
        _ctx(), json.dumps({"name": "demo", "path": "references/lanes/01.md"})
    )
    assert out == "LANE BODY"


@pytest.mark.asyncio
async def test_read_skill_file_rejects_traversal(_bundled_skill):
    """A path escaping the skill dir must be refused, not read."""
    import json

    tool = _skill_file_tool(_bundled_skill)
    out = await tool.on_invoke_tool(
        _ctx(), json.dumps({"name": "demo", "path": "../../../etc/passwd"})
    )
    assert out.startswith("Access denied:")


@pytest.mark.asyncio
async def test_read_skill_file_reports_missing_file_in_band(_bundled_skill):
    """Failures are RETURNED (a raise would abort the run) and use a prefix
    is_tool_failure recognizes, so the UI renders a failed step."""
    import json

    from openkb.agent.tools import is_tool_failure

    tool = _skill_file_tool(_bundled_skill)
    out = await tool.on_invoke_tool(
        _ctx(), json.dumps({"name": "demo", "path": "references/gone.md"})
    )
    assert is_tool_failure(out)


@pytest.mark.asyncio
async def test_read_skill_file_rejects_unknown_skill(_bundled_skill):
    import json

    from openkb.agent.tools import is_tool_failure

    tool = _skill_file_tool(_bundled_skill)
    out = await tool.on_invoke_tool(
        _ctx(), json.dumps({"name": "nope", "path": "references/guide.md"})
    )
    assert is_tool_failure(out)
