import { useMemo, useState } from "react"
import { useLocation, useNavigate } from "react-router"
import { useTranslation } from "react-i18next"
import { ArrowRight, Library, MessageSquare, Search } from "lucide-react"
import ChatInput, { type SlashCommand } from "@/components/ChatInput"
import { useChatHistory } from "@/hooks/useChatHistory"

function formatWhen(value: string): string {
  if (!value) return ""
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value.replace("T", " ").slice(0, 16) : date.toLocaleString()
}

export default function Home() {
  const { t } = useTranslation(["home", "common"])
  const navigate = useNavigate()
  const location = useLocation() as { state?: { kbId?: string } }
  const { groups, loading, error, reload } = useChatHistory()
  const [selectedKb, setSelectedKb] = useState("")
  const [search, setSearch] = useState("")
  const kbId = selectedKb || location.state?.kbId || groups[0]?.kb.name || ""

  const visible = useMemo(() => {
    const query = search.trim().toLocaleLowerCase()
    return groups
      .map((group) => ({
        ...group,
        sessions: query && !group.kb.name.toLocaleLowerCase().includes(query)
          ? group.sessions.filter((session) => session.title.toLocaleLowerCase().includes(query))
          : group.sessions,
      }))
      .filter((group) => !query || group.kb.name.toLocaleLowerCase().includes(query) || group.sessions.length > 0)
      .sort((a, b) => (b.sessions[0]?.updated_at ?? "").localeCompare(a.sessions[0]?.updated_at ?? ""))
  }, [groups, search])
  const totalChats = groups.reduce((count, group) => count + group.sessions.length, 0)

  const send = (text: string, command: SlashCommand | null) => {
    if (!kbId || (!text.trim() && !command)) return
    navigate("/chat/new", {
      state: { text, commandId: command?.id ?? null, cmd: command?.cmd ?? null, kbId },
    })
  }

  return (
    <div className="flex h-full flex-col">
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto max-w-[1050px] px-5 pb-10 pt-9 lg:px-9">
          <div className="pr-28">
            <div className="mb-2 flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.1em] text-accent-brand">
              <MessageSquare className="size-4" />{t("workspace")}
            </div>
            <h1 className="text-[28px] font-bold tracking-tight">{t("title")}</h1>
            <p className="mt-1 text-[13px] text-muted-foreground">
              {t("subtitle", { chats: totalChats, kbs: groups.length })}
            </p>
          </div>

          <div className="mt-7 flex items-center gap-3">
            <div className="relative min-w-0 flex-1">
              <Search className="absolute left-3 top-1/2 size-4 -translate-y-1/2 text-muted-foreground" />
              <input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={t("searchPlaceholder")}
                aria-label={t("searchPlaceholder")}
                className="h-10 w-full rounded-xl border border-[hsl(var(--glass-border))] bg-background/70 pl-10 pr-3 text-[13px] outline-none focus:ring-2 focus:ring-accent-brand/30"
              />
            </div>
            <button onClick={() => navigate("/kb")} className="inline-flex h-10 items-center gap-2 rounded-xl border border-[hsl(var(--glass-border))] px-3 text-[12px] font-medium hover:bg-accent md:hidden">
              <Library className="size-4" />{t("common:nav.kbs")}
            </button>
          </div>

          {loading && groups.length === 0 && <p className="mt-10 text-sm text-muted-foreground">{t("common:loading")}</p>}
          {error && <div role="alert" className="mt-8 text-sm text-destructive">{t("loadError")} <button onClick={reload} className="underline">{t("common:actions.refresh")}</button></div>}
          {!loading && !error && groups.length === 0 && (
            <div className="mt-12 rounded-2xl border border-dashed border-[hsl(var(--glass-border))] p-8 text-center">
              <Library className="mx-auto size-7 text-muted-foreground" />
              <p className="mt-3 text-sm font-medium">{t("noKbs")}</p>
              <button onClick={() => navigate("/kb")} className="mt-3 text-sm font-semibold text-accent-brand hover:underline">{t("common:nav.kbs")} <ArrowRight className="inline size-3.5" /></button>
            </div>
          )}
          {!loading && groups.length > 0 && visible.length === 0 && <p className="mt-10 text-sm text-muted-foreground">{t("noSearchResults")}</p>}

          <div className="mt-7 space-y-7">
            {visible.map(({ kb, sessions, error: sessionError }) => (
              <section key={kb.name} className="overflow-hidden rounded-2xl border border-[hsl(var(--glass-border))] bg-background/55">
                <div className="flex items-center justify-between gap-3 border-b border-[hsl(var(--glass-border))] bg-muted/25 px-5 py-3.5">
                  <div className="min-w-0">
                    <h2 className="truncate text-[15px] font-bold">{kb.name}</h2>
                    <p className="mt-0.5 text-[11px] text-muted-foreground">{t("groupMeta", { chats: sessions.length, docs: kb.document_count })}</p>
                  </div>
                  <button onClick={() => { setSelectedKb(kb.name); document.querySelector<HTMLTextAreaElement>("main textarea")?.focus() }} className="shrink-0 rounded-lg px-2.5 py-1.5 text-[12px] font-semibold text-accent-brand hover:bg-accent">
                    {t("newChat")}
                  </button>
                </div>
                {sessionError ? <p className="px-5 py-5 text-[12px] text-destructive">{t("sessionsLoadError")} <button onClick={reload} className="underline">{t("common:actions.refresh")}</button></p>
                  : sessions.length === 0 ? <p className="px-5 py-5 text-[12px] text-muted-foreground">{search ? t("noChatsMatch") : t("noChatsInKb")}</p>
                  : sessions.map((session) => (
                    <button
                      key={session.id}
                      onClick={() => navigate(`/chat/${encodeURIComponent(session.id)}`, { state: { kbId: kb.name } })}
                      className="group flex w-full items-center gap-3 border-b border-[hsl(var(--glass-border))] px-5 py-3 text-left last:border-0 hover:bg-accent/50"
                    >
                      <MessageSquare className="size-4 shrink-0 text-muted-foreground" />
                      <span className="min-w-0 flex-1 truncate text-[13px] font-medium">{session.title || t("untitledSession")}</span>
                      <span className="hidden shrink-0 text-[11px] text-muted-foreground sm:block">{t("turns", { count: session.turn_count })}</span>
                      <time className="hidden shrink-0 text-[11px] text-muted-foreground lg:block" dateTime={session.updated_at}>{formatWhen(session.updated_at)}</time>
                      <ArrowRight className="size-4 shrink-0 text-muted-foreground opacity-0 group-hover:opacity-100" />
                    </button>
                  ))}
              </section>
            ))}
          </div>
        </div>
      </div>

      <div className="shrink-0 border-t border-[hsl(var(--glass-border))] glass-2">
        <div className="mx-auto max-w-[1050px] px-5 pb-2 pt-2.5 lg:px-9">
          <ChatInput kbId={kbId} onKbChange={setSelectedKb} onSend={send} />
          <p className="mt-2 text-center text-[11px] text-muted-foreground/70">{t("tagline")}</p>
        </div>
      </div>
    </div>
  )
}
