import { apiFetch, apiStream, type SseEvent } from "./client"
import i18n from "@/lib/i18n"

/**
 * A provenance "source" derived from a `tool_call` the agent made during a
 * turn.
 *
 * This is NOT a model-authored citation — the real backend emits no citations.
 * It is the set of wiki artifacts the agent actually *read*, reconstructed from
 * the live SSE `tool_call` stream via an explicit WHITELIST of tool names
 * (never a blacklist): only tools whose provenance we can name are surfaced;
 * every other tool name is ignored (see {@link toolCallSource}).
 *
 *  - kind `"page"`: a `read_file(path)` call. Clickable — the path resolves to
 *    a real wiki page via `/api/v1/page {kb, path}`.
 *  - kind `"doc"`: a `get_page_content(doc_name, pages)` call against a long
 *    (PageIndex) document's internal JSON metadata. No endpoint serves that, so
 *    it renders as a non-clickable label — still shown, so the answer's
 *    provenance is honest about having drawn on a long document, not only wiki
 *    pages.
 */
export interface Source {
  kind: "page" | "doc" | "search"
  /** Display label: the page path (kind `"page"`), doc name (kind `"doc"`), or
   *  the query text (kind `"search"`). */
  label: string
  /** Wiki-relative page path — present only for kind `"page"`. */
  path?: string
  /** Long-document name — present only for kind `"doc"`. */
  docName?: string
  /** Confluence space key — present when the read came from a project KB's
   *  child space (`read_space_page`), so the page opens against that space
   *  rather than the project's own empty wiki. */
  space?: string
}

/** Backend-verified verbatim text from a wiki/sources/ original document. */
export interface Citation {
  id: string
  space: string
  path: string
  title: string
  quote: string
  start: number
  end: number
}

export interface CitationSource {
  title: string
  content: string
  start: number
  end: number
}

export function getCitationSource(kb: string, citation: Citation): Promise<CitationSource> {
  return apiFetch<CitationSource>("/api/v1/citation/source", {
    body: { kb, path: citation.path, quote: citation.quote, space: citation.space },
  })
}

export function parseCitations(value: unknown): Citation[] {
  if (!Array.isArray(value)) return []
  const seen = new Set<string>()
  const citations: Citation[] = []
  for (const item of value) {
    if (!item || typeof item !== "object") continue
    const c = item as Partial<Citation>
    if (
      typeof c.id !== "string" || typeof c.path !== "string" ||
      !/^sources\/[^/]+\.(md|json)$/.test(c.path) || typeof c.quote !== "string" ||
      typeof c.title !== "string" || typeof c.space !== "string" ||
      typeof c.start !== "number" || typeof c.end !== "number" ||
      seen.has(c.id)
    ) continue
    seen.add(c.id)
    citations.push(c as Citation)
  }
  return citations
}

/**
 * One item in a turn's ORDERED, interleaved trace, preserving SSE arrival
 * order: a chunk of the model's narration/answer text, or one tool read.
 *
 *  - `text`: a contiguous run of `delta` text (one block of narration, or the
 *    final answer). Consecutive deltas coalesce into the same trailing step.
 *  - `tool`: one whitelisted read (`toolCallSource`). `done` flips true once a
 *    LATER tool call arrives (the previous read must have completed) or the
 *    turn settles (`final`/`done`), driving the ✅-when-resolved affordance.
 *    `ok` is false when the backend's `tool_result` reported the read failed
 *    (missing path, unknown space); `done && ok !== false` is the only state
 *    that earns a ✅. Undefined means "no result seen" — an older persisted
 *    trace, or a stream that ended before the result arrived.
 */
export type TurnStep =
  | { kind: "text"; text: string }
  | { kind: "tool"; source: Source; done: boolean; ok?: boolean }

/**
 * Accumulated state for ONE assistant turn, folded from the SSE event stream.
 *
 * Sources are per-turn: dedupe happens within this object only, never across a
 * whole session. The same page read again in a later turn is a distinct, valid
 * source and must not be suppressed by an earlier turn.
 */
export interface ChatTurnState {
  /** Answer text: accumulated from `delta` events (progressive) and confirmed
   *  by the `final` event. Kept flat alongside `steps` for session restore and
   *  any other consumer that wants the whole answer as one string. */
  answer: string
  /** Ordered, interleaved trace of narration text and tool reads, in SSE
   *  arrival order — the source of truth for step-by-step rendering. */
  steps: TurnStep[]
  /** Whitelisted, per-turn-deduped provenance, in first-seen order. */
  sources: Source[]
  citations: Citation[]
  /** Most recent in-progress read, for a live "reading X…" indicator; null once
   *  the turn is idle or finished. */
  reading: Source | null
  /** Chat session id — only chat's `final` carries it; query turns stay null. */
  sessionId: string | null
  /** Where a saved query answer landed (query's `final.saved_path`). */
  savedPath: string | null
  /** Turn count from chat's `final`. */
  turnCount: number | null
  /** True once the terminal `done` event arrives. */
  done: boolean
  /** Error message from an `error` event, else null. */
  error: string | null
  /** Viewable HTML files this turn produced via the chat agent's write_file
   *  tool (from `artifact` SSE events). `kb` is captured at fold time (the
   *  active KB when the artifact event arrived), NOT re-attached at render
   *  time — the top-level `kb` state can change mid-session (KB dropdown
   *  switch), and a historical turn's file must keep pointing at the KB it
   *  was actually produced under. */
  artifacts: { path: string; name: string; kb: string }[]
}

export function initialTurnState(): ChatTurnState {
  return {
    answer: "",
    steps: [],
    sources: [],
    citations: [],
    reading: null,
    sessionId: null,
    savedPath: null,
    turnCount: null,
    done: false,
    error: null,
    artifacts: [],
  }
}

/** Normalize a wiki path for dedupe: strip a leading `./`, surrounding slashes,
 *  and a trailing `.md` so `summaries/x` and `summaries/x.md` collapse to one. */
function normalizePath(path: string): string {
  return path
    .trim()
    .replace(/^\.\//, "")
    .replace(/^\/+|\/+$/g, "")
    .replace(/\.md$/i, "")
}

/** Index of the LAST element satisfying `pred`, or -1. (Array.prototype.findLastIndex
 *  needs a newer lib target than this project's tsconfig sets.) */
function findLastIndex<T>(items: T[], pred: (item: T) => boolean): number {
  for (let i = items.length - 1; i >= 0; i--) {
    if (pred(items[i])) return i
  }
  return -1
}

function sourceKey(s: Source): string {
  if (s.kind === "page") return `page:${s.space ?? ""}:${normalizePath(s.path ?? "")}`
  if (s.kind === "search") return `search:${s.label.trim().toLowerCase()}`
  return `doc:${(s.docName ?? "").trim()}`
}

/**
 * The WHITELIST. Turn a `tool_call` event's `data` into a {@link Source}, or
 * `null` to drop it.
 *
 * Only `read_file`, `get_page_content`, `read_space_page` and `search_spaces`
 * are recognised; any other tool name (`get_image`, `list_spaces`, or a tool
 * added to the agent later) yields `null` and is ignored. This is deliberately
 * a whitelist, not a blacklist: an unknown future tool never becomes a broken
 * or misleading chip.
 *
 * `arguments` is a JSON string — parsed defensively; a parse failure or a
 * missing required field yields `null` rather than a half-formed source.
 */
export function toolCallSource(data: unknown): Source | null {
  const d = (data ?? {}) as { name?: unknown; arguments?: unknown }
  const name = d.name
  if (
    name !== "read_file" &&
    name !== "get_page_content" &&
    name !== "read_space_page" &&
    name !== "search_spaces"
  ) {
    return null
  }

  let args: Record<string, unknown> = {}
  const raw = d.arguments
  if (typeof raw === "string" && raw.trim()) {
    try {
      args = JSON.parse(raw) as Record<string, unknown>
    } catch {
      return null
    }
  } else if (raw && typeof raw === "object") {
    args = raw as Record<string, unknown>
  }

  if (name === "read_file") {
    const path = typeof args.path === "string" ? args.path.trim() : ""
    if (!path) return null
    return { kind: "page", label: path, path }
  }
  if (name === "read_space_page") {
    const path = typeof args.path === "string" ? args.path.trim() : ""
    const space = typeof args.space === "string" ? args.space.trim() : ""
    if (!path || !space) return null
    // Label carries the space so provenance reads unambiguously across a
    // project whose spaces can hold same-named pages.
    return { kind: "page", label: `${space}/${path}`, path, space }
  }
  if (name === "search_spaces") {
    const query = typeof args.query === "string" ? args.query.trim() : ""
    if (!query) return null
    return { kind: "search", label: query }
  }
  // get_page_content
  const docName = typeof args.doc_name === "string" ? args.doc_name.trim() : ""
  if (!docName) return null
  return { kind: "doc", label: docName, docName }
}

/** Append a source to a per-turn list, deduped by normalized key. First-seen
 *  order is preserved. */
function mergeSource(list: Source[], s: Source): Source[] {
  const key = sourceKey(s)
  return list.some((x) => sourceKey(x) === key) ? list : [...list, s]
}

/** Append `delta` text to the CURRENT trailing text step, or start a new text
 *  step when the last step is a tool step (or the trace is empty). */
function appendDelta(steps: TurnStep[], text: string): TurnStep[] {
  const last = steps[steps.length - 1]
  if (last && last.kind === "text") {
    return [...steps.slice(0, -1), { kind: "text", text: last.text + text }]
  }
  return [...steps, { kind: "text", text }]
}

/** Flip every still-in-flight tool step to `done` (a fresh copy of any changed
 *  step; unchanged steps keep their identity). Exported so a stream that throws
 *  (see ChatSession's runTurn catch/finally) can settle any spinner still
 *  spinning on an unfinished tool read. */
export function markToolStepsDone(steps: TurnStep[]): TurnStep[] {
  return steps.map((s) => (s.kind === "tool" && !s.done ? { ...s, done: true } : s))
}

/** Rebuild a restored turn's TurnStep[] from its persisted trace. Text steps
 *  map directly; tool steps go through the same read-only whitelist used live
 *  (`toolCallSource`), so a non-read tool (e.g. write_file) yields null and is
 *  dropped — restore renders exactly what the live trace showed. Reads are
 *  already settled (done). */
export function stepsFromTrace(trace: PersistedTraceStep[]): TurnStep[] {
  const out: TurnStep[] = []
  for (const s of trace) {
    if (s.kind === "text") {
      if (typeof s.text === "string" && s.text) out.push({ kind: "text", text: s.text })
    } else if (s.kind === "tool") {
      const src = toolCallSource({ name: s.name, arguments: s.arguments })
      // `ok` is persisted only for reads that FAILED (see iter_chat_turn_events);
      // its absence on an older trace means "outcome unknown", which renders the
      // same as a plain settled read.
      if (src) out.push({ kind: "tool", source: src, done: true, ...(s.ok === false ? { ok: false } : {}) })
    }
  }
  return out
}

/**
 * Defensively derive sources from a `final.history` array (the Agents SDK
 * `to_input_list()` record), if one is ever present.
 *
 * The current backend does NOT forward `history` over SSE — `_stream_query` and
 * `iter_chat_turn_events` deliberately strip it from the `final` frame to avoid
 * shipping large file/page contents to the browser — so this returns `null`
 * today and the live-accumulated `sources` are kept. It is retained as a
 * forward-compatible *preference*: if a future backend includes `history`, it
 * becomes the authoritative list and a dropped mid-stream `tool_call` can no
 * longer lose a source.
 */
export function sourcesFromHistory(history: unknown): Source[] | null {
  if (!Array.isArray(history)) return null
  let out: Source[] = []
  for (const item of history) {
    if (!item || typeof item !== "object") continue
    const record = item as { type?: unknown; name?: unknown; arguments?: unknown }
    const isCall =
      record.type === "function_call" ||
      (typeof record.name === "string" && "arguments" in record)
    if (!isCall) continue
    const src = toolCallSource({ name: record.name, arguments: record.arguments })
    if (src) out = mergeSource(out, src)
  }
  return out
}

/**
 * Fold one SSE event into the running turn state. Callers apply this per event
 * as the stream arrives (calling `setState`), so the UI reveals the answer and
 * the "reading" indicator live — no artificial delay.
 *
 * `kb` is the KB active at fold time (captured once by the caller at turn
 * start, e.g. `runTurn`'s `activeKb`), baked into any `artifact` produced this
 * turn — never re-derived from render-time state, so a later KB switch can't
 * retroactively repoint a historical turn's file artifact at the wrong KB.
 *
 * Real backend event shapes (verified against `openkb/api_helpers.py`):
 *   - `delta`     → `{ text }`            (incremental answer text)
 *   - `tool_call`   → `{ name, arguments }` (arguments is a JSON string)
 *   - `tool_result` → `{ name, arguments, ok }` — the call's honest outcome.
 *                     Read tools return their failures as text rather than
 *                     raising, so `tool_call` alone never meant the read
 *                     succeeded; this is what settles that.
 *   - `final`     → query: `{ answer, saved_path }`;
 *                   chat:  `{ answer, session_id, turn_count }`
 *   - `error`     → `{ message }`
 *   - `artifact`  → `{ kind: "file", path, name }` (chat only, from a confirmed
 *                   `write_file` of a viewable `output/**.html`)
 *   - `done`      → `{}`
 *   - `start`     → ignored
 */
export function foldSseEvent(state: ChatTurnState, event: SseEvent, kb: string): ChatTurnState {
  const data = (event?.data ?? {}) as Record<string, unknown>
  switch (event?.event) {
    case "delta": {
      const text = typeof data.text === "string" ? data.text : ""
      if (!text) return state
      return { ...state, answer: state.answer + text, steps: appendDelta(state.steps, text) }
    }
    case "tool_call": {
      const src = toolCallSource(data)
      if (!src) return state
      // A new tool call means the previous read completed: settle prior
      // in-flight tool steps, then push this read as the new in-flight step.
      const steps: TurnStep[] = [
        ...markToolStepsDone(state.steps),
        { kind: "tool", source: src, done: false },
      ]
      // A search is a step, not provenance: it names what was looked for, not
      // a wiki artifact the answer drew on. Only the pages actually read
      // belong in `sources`.
      const sources = src.kind === "search" ? state.sources : mergeSource(state.sources, src)
      return { ...state, reading: src, sources, steps }
    }
    case "tool_result": {
      // The honest outcome of the most recent matching call. Successes need no
      // patch (a settled step with `ok` undefined already renders as done), so
      // only a failure is folded in — that's what the ✅ was lying about.
      if (data.ok !== false) return state
      const name = typeof data.name === "string" ? data.name : ""
      const src = toolCallSource({ name, arguments: data.arguments })
      if (!src) return state
      const key = sourceKey(src)
      const idx = findLastIndex(
        state.steps,
        (s) => s.kind === "tool" && sourceKey(s.source) === key,
      )
      if (idx < 0) return state
      const target = state.steps[idx] as Extract<TurnStep, { kind: "tool" }>
      const steps = [...state.steps]
      steps[idx] = { ...target, done: true, ok: false }
      // A failed read is not provenance — drop it from `sources` so the answer
      // never cites a page the agent could not actually open.
      return { ...state, steps, sources: state.sources.filter((s) => sourceKey(s) !== key) }
    }
    case "final": {
      const histSources = sourcesFromHistory(data.history)
      const authoritative = typeof data.answer === "string" && data.answer ? data.answer : ""
      const answer = authoritative || state.answer
      // All reads are done once the turn finalizes. If a definitive answer
      // arrived, make the trailing text step reflect it (over accumulated
      // narration); otherwise keep the streamed trace as-is.
      let steps = markToolStepsDone(state.steps)
      // `authoritative` (final.answer) is the FULL concatenation of every
      // streamed text delta (narration + answer); the streamed trace already
      // ends with the answer run, so do NOT overwrite the trailing step with it
      // (that would duplicate narration whenever tool reads split the text).
      // Only inject it when the model streamed no NON-WHITESPACE text: a
      // whitespace-only delta (" "/"\n") still creates a text step but renders
      // as null in AssistantMessage, so without this the user would see tool
      // chips and no answer at all.
      if (authoritative && !steps.some((s) => s.kind === "text" && s.text.trim())) {
        steps = [...steps, { kind: "text", text: authoritative }]
      }
      return {
        ...state,
        answer,
        steps,
        sources: histSources ?? state.sources,
        citations: parseCitations(data.citations),
        reading: null,
        sessionId:
          typeof data.session_id === "string" ? data.session_id : state.sessionId,
        savedPath: typeof data.saved_path === "string" ? data.saved_path : state.savedPath,
        turnCount: typeof data.turn_count === "number" ? data.turn_count : state.turnCount,
      }
    }
    case "error": {
      const message = typeof data.message === "string" ? data.message : i18n.t("common:errors.requestFailed")
      return { ...state, reading: null, error: message }
    }
    case "artifact": {
      // Forward-compat guard: only `kind: "file"` artifacts are folded here.
      // A future non-file `kind` must not be silently mis-tagged as a file.
      if (data.kind !== "file") return state
      const path = typeof data.path === "string" ? data.path.trim() : ""
      const name = typeof data.name === "string" ? data.name.trim() : ""
      if (!path || !name) return state
      if (state.artifacts.some((x) => x.path === path)) return state
      return { ...state, artifacts: [...state.artifacts, { path, name, kb }] }
    }
    case "done":
      return { ...state, reading: null, done: true, steps: markToolStepsDone(state.steps) }
    default:
      // "start" and any unknown event: ignore.
      return state
  }
}

// --- Stream wrappers over apiStream --------------------------------------

/**
 * One-off wiki Q&A (`/ask`): streams `delta`/`tool_call`/`final`. Stateless —
 * no chat session is created (`final` carries `saved_path`, never a session id).
 */
export async function* streamQuery(
  kb: string,
  question: string,
  opts: { save?: boolean } = {},
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  yield* apiStream(
    "/api/v1/query",
    {
      kb,
      question,
      stream: true,
      save: opts.save ?? false,
    },
    signal,
  )
}

/**
 * Multi-turn chat. A null `sessionId` starts a new session; the `final` event
 * carries the created `session_id`, which the caller should adopt for
 * subsequent turns.
 */
export async function* streamChat(
  kb: string,
  sessionId: string | null,
  message: string,
  signal?: AbortSignal,
): AsyncGenerator<SseEvent> {
  yield* apiStream(
    "/api/v1/chat",
    {
      kb,
      session_id: sessionId,
      message,
      stream: true,
    },
    signal,
  )
}

// --- Session listing / loading -------------------------------------------

export interface ChatSessionItem {
  id: string
  title: string
  turn_count: number
  updated_at: string
  model: string
}

export interface ChatSessionListResponse {
  kb: string
  sessions: ChatSessionItem[]
}

/** List a single KB's chat sessions (`/api/v1/chat/sessions`). There is no
 *  cross-KB aggregate endpoint; callers merge per-KB results client-side. */
export function listSessions(kb: string): Promise<ChatSessionListResponse> {
  return apiFetch<ChatSessionListResponse>("/api/v1/chat/sessions", { body: { kb } })
}

/** One persisted trace step from loadSession (parallel to the live TurnStep,
 *  but a tool step keeps the RAW name/arguments so the read-only whitelist is
 *  re-applied on restore, exactly as live). */
export interface PersistedTraceStep {
  kind: "text" | "tool"
  text?: string
  name?: string
  arguments?: string
  /** Present (and `false`) only on a tool step whose read FAILED. Absent on a
   *  successful read and on any trace persisted before this field existed. */
  ok?: boolean
}

export interface ChatSessionLoad {
  session_id: string
  title: string
  turn_count: number
  user_turns: string[]
  assistant_texts: string[]
  /** Parallel to assistant_texts by index; an empty inner array means "no trace
   *  for this turn — fall back to the flat assistant_texts entry". Absent from a
   *  backend too old to send it. */
  assistant_traces?: PersistedTraceStep[][]
  assistant_citations?: Citation[][]
}

/** Load one session's turns for restore-on-reload (`/api/v1/chat/sessions/load`).
 *  Returns answer text only — per-turn sources are live-derived and not
 *  persisted, so restored turns render without source chips. */
export function loadSession(kb: string, sessionId: string): Promise<ChatSessionLoad> {
  return apiFetch<ChatSessionLoad>("/api/v1/chat/sessions/load", {
    body: { kb, session_id: sessionId },
  })
}
