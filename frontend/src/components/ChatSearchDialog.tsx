import { useMemo } from "react"
import { useNavigate } from "react-router"
import { useTranslation } from "react-i18next"
import { Library, MessageSquare, Search } from "lucide-react"
import { Dialog, DialogContent, DialogDescription, DialogTitle } from "@/components/ui/dialog"
import type { ChatHistoryGroup } from "@/hooks/useChatHistory"

interface Props {
  open: boolean
  onOpenChange: (open: boolean) => void
  query: string
  onQueryChange: (query: string) => void
  groups: ChatHistoryGroup[]
  loading: boolean
  error: string | null
}

export default function ChatSearchDialog({
  open, onOpenChange, query, onQueryChange, groups, loading, error,
}: Props) {
  const navigate = useNavigate()
  const { t } = useTranslation(["home", "common"])
  const term = query.trim().toLocaleLowerCase()
  const matchingKbs = useMemo(
    () => term ? groups.filter(({ kb }) => kb.name.toLocaleLowerCase().includes(term)) : [],
    [groups, term],
  )
  const sessions = useMemo(
    () => groups.flatMap(({ kb, sessions: items }) =>
      items.map((session) => ({ ...session, kb: kb.name })))
      .filter((session) => !term ||
        session.title.toLocaleLowerCase().includes(term) ||
        session.kb.toLocaleLowerCase().includes(term))
      .sort((a, b) => b.updated_at.localeCompare(a.updated_at))
      .slice(0, term ? undefined : 15),
    [groups, term],
  )
  const close = () => { onOpenChange(false); onQueryChange("") }

  return (
    <Dialog open={open} onOpenChange={(next) => { onOpenChange(next); if (!next) onQueryChange("") }}>
      <DialogContent className="flex max-h-[min(75vh,650px)] w-[min(680px,calc(100vw-2rem))] flex-col gap-0 overflow-hidden rounded-2xl p-0 sm:max-w-[680px]">
        <DialogTitle className="sr-only">{t("searchTitle")}</DialogTitle>
        <DialogDescription className="sr-only">{t("searchDescription")}</DialogDescription>
        <div className="flex shrink-0 items-center gap-3 border-b border-[hsl(var(--glass-border))] px-5 pr-14">
          <Search className="size-5 shrink-0 text-muted-foreground" />
          <input
            value={query}
            onChange={(event) => onQueryChange(event.target.value)}
            placeholder={t("searchPlaceholder")}
            aria-label={t("searchPlaceholder")}
            className="h-16 min-w-0 flex-1 bg-transparent text-[15px] outline-none placeholder:text-muted-foreground"
          />
        </div>
        <div className="min-h-0 overflow-y-auto p-3">
          {loading && groups.length === 0 && <p className="px-3 py-6 text-sm text-muted-foreground">{t("common:loading")}</p>}
          {error && <p role="alert" className="px-3 py-6 text-sm text-destructive">{t("loadError")}</p>}
          {matchingKbs.length > 0 && (
            <div className="mb-2">
              <p className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{t("common:nav.kbs")}</p>
              {matchingKbs.map(({ kb, sessions: kbSessions }) => (
                <button
                  key={kb.name}
                  onClick={() => { navigate(`/kb/${encodeURIComponent(kb.name)}`); close() }}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[13px] hover:bg-accent"
                >
                  <Library className="size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate font-medium">{kb.name}</span>
                  <span className="text-[11px] text-muted-foreground">{t("groupMeta", { chats: kbSessions.length, docs: kb.document_count })}</span>
                </button>
              ))}
            </div>
          )}
          {sessions.length > 0 && (
            <>
              <p className="px-3 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted-foreground">{term ? t("searchResults") : t("recentSessions")}</p>
              {sessions.map((session) => (
                <button
                  key={`${session.kb}/${session.id}`}
                  onClick={() => {
                    navigate(`/chat/${encodeURIComponent(session.id)}`, { state: { kbId: session.kb } })
                    close()
                  }}
                  className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-[13px] hover:bg-accent"
                >
                  <MessageSquare className="size-4 shrink-0 text-muted-foreground" />
                  <span className="min-w-0 flex-1 truncate">{session.title || t("untitledSession")}</span>
                  <span className="hidden max-w-[130px] shrink-0 truncate text-[11px] text-muted-foreground sm:block">{session.kb}</span>
                </button>
              ))}
            </>
          )}
          {!loading && !error && matchingKbs.length === 0 && sessions.length === 0 && (
            <p className="px-3 py-8 text-center text-sm text-muted-foreground">
              {groups.some((group) => group.error) ? t("sessionsLoadError") : term ? t("noSearchResults") : t("noChatsYet")}
            </p>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
