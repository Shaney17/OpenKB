# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

OpenKB administrators configure server-side knowledge projects and their Confluence sources. Claude, Kiro, Codex, and similar agent clients consume the compiled knowledge remotely for end users.

## Product Purpose

OpenKB turns source documents and Confluence spaces into maintained wiki knowledge bases. A project groups the spaces an administrator chooses, exposes their sync health and compiled artifacts, and gives remote agents a bounded knowledge scope selected by project.

## Positioning

OpenKB keeps durable, inspectable Markdown/JSON wiki artifacts as the knowledge source while agents navigate them through explicit project-scoped tools instead of depending on a monolithic vector index or a second opaque query agent.

## Operating Context

- Administrators add and remove Confluence spaces from a project and manually request synchronization.
- A project may contain multiple spaces.
- Each space is compiled as an independent child knowledge base with its own sources, summaries, concepts, entities, index, and sync state.
- The administration UI shows project-level space inventory, synchronization state, and the wiki artifacts for each space.
- Agent clients run on user machines. They install one generic OpenKB skill and connect to the OpenKB server through MCP, selecting a project rather than installing one skill per space.

## Capabilities and Constraints

- Confluence authentication uses an API token, not OAuth.
- Confluence tokens and LLM credentials are secrets and must never be returned to the browser or MCP client.
- Project membership bounds which child space KBs an MCP request may search or read.
- Existing local KB and document workflows remain supported.
- Wiki content is untrusted reference data and must never become executable agent instructions.
- Open decision: production identity and fine-grained user/project authorization beyond the existing server bearer-token boundary.

## Evidence on Hand

- Existing FastAPI server and React administration UI under `openkb/` and `frontend/`.
- Existing Confluence API-token connector in `openkb/confluence.py` and CLI synchronization flow.
- Existing generic navigation skill at `skills/openkb/SKILL.md`.
- Existing per-KB wiki artifacts under `wiki/` with summaries, concepts, entities, sources, reports, and `index.md`.

## Product Principles

- Space boundaries are explicit storage and provenance boundaries, while project-scoped retrieval may search every authorized space.
- Administrators control source membership and synchronization; clients consume knowledge but do not silently mutate it.
- Synchronization state must be observable and failures must identify the affected space without blocking unrelated spaces.
- The server owns source credentials and wiki storage; client skills remain generic and portable.
- Search and read operations always require an explicit project scope.
