import { useState } from "react"
import { useLocation, useNavigate } from "react-router"
import { useTranslation } from "react-i18next"
import { Library, Search } from "lucide-react"
import ChatInput, { type SlashCommand } from "@/components/ChatInput"
import ChatSearchDialog from "@/components/ChatSearchDialog"
import { useChatHistory } from "@/hooks/useChatHistory"

export default function Home() {
  const { t } = useTranslation(["home", "common"])
  const navigate = useNavigate()
  const location = useLocation() as ReturnType<typeof useLocation> & { state?: { kbId?: string } }
  const { groups, loading, error, reload } = useChatHistory()
  const [selection, setSelection] = useState<{ locationKey: string; kb: string } | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [searchQuery, setSearchQuery] = useState("")
  // A new navigation to "/" with a KB from the sidebar takes precedence over
  // any selection made in an earlier visit to the same route.
  const kbId = (selection?.locationKey === location.key ? selection.kb : "") ||
    location.state?.kbId || groups[0]?.kb.name || ""

  const send = (text: string, command: SlashCommand | null) => {
    if (!kbId || (!text.trim() && !command)) return
    navigate("/chat/new", {
      state: { text, commandId: command?.id ?? null, cmd: command?.cmd ?? null, kbId },
    })
  }

  return (
    <div className="flex h-full items-center justify-center overflow-y-auto px-5 py-12">
      <div className="w-full max-w-[760px]">
        <div className="mb-8 text-center">
          <h1 className="text-[30px] font-bold tracking-tight sm:text-[36px]">{t("newChat")}</h1>
          <p className="mt-2 text-[14px] text-muted-foreground">{t("newChatSubtitle")}</p>
        </div>
        {loading && groups.length === 0 && <p className="mb-4 text-center text-sm text-muted-foreground">{t("common:loading")}</p>}
        {error && <p role="alert" className="mb-4 text-center text-sm text-destructive">{t("loadError")} <button onClick={reload} className="underline">{t("common:actions.refresh")}</button></p>}
        {!loading && !error && groups.length === 0 && (
          <button onClick={() => navigate("/kb")} className="mx-auto mb-5 flex items-center gap-2 text-sm font-medium text-accent-brand hover:underline">
            <Library className="size-4" />{t("noKbs")}
          </button>
        )}
        <ChatInput
          kbId={kbId}
          onKbChange={(kb) => setSelection({ locationKey: location.key, kb })}
          onSend={send}
          autoFocus
        />
        <p className="mt-4 text-center text-[11px] text-muted-foreground/70">{t("tagline")}</p>
        <button
          onClick={() => { setSearchQuery(""); setSearchOpen(true) }}
          className="mx-auto mt-5 flex items-center gap-2 text-[12px] text-muted-foreground hover:text-foreground md:hidden"
        ><Search className="size-3.5" />{t("searchPlaceholder")}</button>
      </div>
      <ChatSearchDialog
        open={searchOpen}
        onOpenChange={setSearchOpen}
        query={searchQuery}
        onQueryChange={setSearchQuery}
        groups={groups}
        loading={loading}
        error={error}
      />
    </div>
  )
}
