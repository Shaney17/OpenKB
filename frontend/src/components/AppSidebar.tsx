import { useState } from "react"
import { NavLink, useLocation, useNavigate } from "react-router"
import { useTranslation } from "react-i18next"
import { ChevronDown, Library, Plus, Search, Settings2 } from "lucide-react"
import CreateKbDialog from "@/components/CreateKbDialog"
import ChatSearchDialog from "@/components/ChatSearchDialog"
import { useChatHistory } from "@/hooks/useChatHistory"
import { cn } from "@/lib/utils"

export default function AppSidebar() {
  const navigate = useNavigate()
  const location = useLocation()
  const { t } = useTranslation(["common", "home"])
  const { groups, loading, error, reload } = useChatHistory()
  const [expanded, setExpanded] = useState<Record<string, boolean>>({})
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  const openSearch = (query = "") => { setSearchQuery(query); setSearchOpen(true) }
  const activeKb = (location.state as { kbId?: string } | null)?.kbId
  const activeId = location.pathname.startsWith("/chat/")
    ? decodeURIComponent(location.pathname.slice("/chat/".length)) : ""

  const navClass = ({ isActive }: { isActive: boolean }) => cn(
    "flex h-9 items-center gap-2.5 rounded-apple-sm px-3 text-[13.5px] font-medium transition-colors",
    isActive ? "bg-accent text-accent-foreground shadow-sm" : "text-muted-foreground hover:bg-accent/60 hover:text-foreground",
  )

  return (
    <aside className="glass m-2 mr-0 hidden w-[266px] shrink-0 flex-col rounded-apple-lg px-3 pb-3 pt-2 md:flex">
      <div className="mb-5 flex h-10 items-center gap-2 px-2">
        <div className="grid size-6 place-items-center rounded-apple-sm bg-accent-brand text-[13px] font-extrabold text-white">K</div>
        <div className="text-[15px] font-bold tracking-tight">OpenKB Studio</div>
      </div>

      <div className="flex items-center justify-between px-3 text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
        {t("nav.kbs")}
        <CreateKbDialog>
          <button aria-label={t("actions.newKb")} title={t("actions.newKb")} className="rounded p-1 hover:bg-accent hover:text-foreground">
            <Plus className="size-3.5" />
          </button>
        </CreateKbDialog>
      </div>
      <nav className="mt-1">
        <NavLink to="/kb" className={navClass}><Library className="size-4" />{t("nav.allKbs")}</NavLink>
      </nav>

      <div className="mt-6 flex items-center justify-between px-3 text-[11px] font-bold uppercase tracking-[0.12em] text-muted-foreground">
        {t("nav.chatHistory")}
        <button onClick={() => openSearch()} aria-label={t("home:searchTitle")} title={t("home:searchTitle")} className="rounded p-1 hover:bg-accent hover:text-foreground">
          <Search className="size-3.5" />
        </button>
      </div>
      <nav className="mt-1 min-h-0 flex-1 overflow-y-auto">
        <NavLink to="/" end className={navClass}><Plus className="size-4" />{t("nav.newChat")}</NavLink>
        {loading && groups.length === 0 && <p className="px-3 py-3 text-xs text-muted-foreground">{t("loading")}</p>}
        {error && <button onClick={reload} className="px-3 py-2 text-left text-xs text-destructive underline">{t("home:loadError")}</button>}
        {groups.map(({ kb, sessions, error: sessionError }) => {
          const isOpen = expanded[kb.name] ?? true
          return (
            <div key={kb.name} className="mt-2">
              <div className="group flex items-center rounded-apple-sm hover:bg-accent/60">
                <button
                  onClick={() => setExpanded((current) => ({ ...current, [kb.name]: !isOpen }))}
                  aria-expanded={isOpen}
                  aria-label={`${kb.name}: ${t("nav.chatHistory")}`}
                  className="flex min-w-0 flex-1 items-center gap-2 px-3 py-2 text-left text-[12.5px] font-semibold"
                >
                  <ChevronDown className={cn("size-3.5 shrink-0 text-muted-foreground transition-transform", !isOpen && "-rotate-90")} />
                  <span className="truncate">{kb.name}</span>
                  <span className="ml-auto text-[11px] font-normal tabular-nums text-muted-foreground">{sessions.length}</span>
                </button>
                <button
                  onClick={() => navigate("/", { state: { kbId: kb.name } })}
                  title={t("home:newChatInKb", { kb: kb.name })}
                  aria-label={t("home:newChatInKb", { kb: kb.name })}
                  className="mr-1 rounded p-1 text-muted-foreground opacity-0 hover:bg-accent hover:text-foreground group-hover:opacity-100 focus:opacity-100"
                ><Plus className="size-3.5" /></button>
              </div>
              {isOpen && (
                <div className="ml-5 border-l border-[hsl(var(--glass-border))] pl-1">
                  {sessionError && <button onClick={reload} className="px-3 py-2 text-xs text-destructive underline">{t("home:sessionsLoadError")}</button>}
                  {!sessionError && sessions.length === 0 && <p className="px-3 py-2 text-[11px] text-muted-foreground">{t("home:noChatsInKb")}</p>}
                  {sessions.slice(0, 12).map((session) => (
                    <NavLink
                      key={session.id}
                      to={`/chat/${encodeURIComponent(session.id)}`}
                      state={{ kbId: kb.name }}
                      title={session.title || t("home:untitledSession")}
                      className={cn(
                        "block truncate rounded-apple-sm px-3 py-1.5 text-[12.5px] text-muted-foreground hover:bg-accent/60 hover:text-foreground",
                        activeId === session.id && activeKb === kb.name && "bg-accent text-foreground",
                      )}
                    >{session.title || t("home:untitledSession")}</NavLink>
                  ))}
                  {sessions.length > 12 && <button onClick={() => openSearch(kb.name)} className="px-3 py-2 text-[11px] font-semibold text-accent-brand hover:underline">{t("home:viewAllChats", { total: sessions.length })}</button>}
                </div>
              )}
            </div>
          )
        })}
      </nav>

      <div className="border-t border-[hsl(var(--glass-border))] pt-2">
        <NavLink to="/settings" className={navClass}><Settings2 className="size-4" />{t("nav.settings")}</NavLink>
      </div>
      <ChatSearchDialog open={searchOpen} onOpenChange={setSearchOpen} query={searchQuery} onQueryChange={setSearchQuery} groups={groups} loading={loading} error={error} />
    </aside>
  )
}
