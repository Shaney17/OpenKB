import { Routes, Route, useParams } from "react-router"
import { MotionConfig } from "motion/react"
import AppSidebar from "@/components/AppSidebar"
import TitleBar from "@/components/TitleBar"
import { ThemeToggle } from "@/lib/theme"
import { LanguageToggle } from "@/lib/language"
import { cn } from "@/lib/utils"
import { Toaster } from "@/components/ui/sonner"
import Home from "@/pages/Home"
import ChatSession from "@/pages/ChatSession"
import KbList from "@/pages/KbList"
import KbDetail from "@/pages/KbDetail"
import Settings from "@/pages/Settings"
import ConfluenceSpaces from "@/pages/ConfluenceSpaces"

/** Remount KbDetail per KB so its page/tree state resets cleanly on nav. */
function KbDetailRoute() {
  const { id = "" } = useParams()
  return <KbDetail key={id} />
}

export default function App() {
  const isDesktopShell =
    typeof (window as { __OPENKB_DESKTOP__?: unknown }).__OPENKB_DESKTOP__ !== "undefined"

  return (
    <MotionConfig reducedMotion="user">
      <div className="ambient-ground h-screen w-screen flex overflow-hidden">
        {isDesktopShell && (
          <div className="absolute top-0 inset-x-0 z-50">
            <TitleBar />
          </div>
        )}
        <div className="flex flex-1 min-h-0 w-full">
          <AppSidebar />
          <main className="relative flex-1 min-w-0 overflow-hidden">
            {/* Global floating chrome cluster: overlays content on every route
                (not the sidebar). It owns a reserved top-right "chrome lane"
                (~112px from main's right edge) sized for the theme toggle NOW
                plus Sub-project H's future i18n switcher + gaps. Page-level
                right-anchored controls reserve that lane with `pr-28` so they
                always clear the pill — see KbList's header row and KbDetail's
                gear row. Clears the desktop TitleBar via a top offset. */}
            <div
              className={cn(
                "absolute right-3 z-40 flex items-center gap-1 rounded-full glass px-1 py-1",
                isDesktopShell ? "top-10" : "top-2.5",
              )}
            >
              <ThemeToggle className="text-muted-foreground hover:text-foreground transition-colors" />
              <LanguageToggle className="text-muted-foreground hover:text-foreground transition-colors" />
            </div>
            <Routes>
              <Route path="/" element={<Home />} />
              {/* No key={id}: ChatSession must NOT remount when runTurn adopts a
                  real session id mid-turn (the new→/chat/<sid> self-navigate) —
                  a remount there would abort the live stream and drop the
                  just-finished turn's artifact cards. Its restore effect instead
                  re-runs on an `id` change and reloads only when navigating to a
                  DIFFERENT saved session, so switching /chat/A→/chat/B still
                  shows the right one. */}
              <Route path="/chat/:id" element={<ChatSession />} />
              <Route path="/kb" element={<KbList />} />
              <Route path="/kb/:id" element={<KbDetailRoute />} />
              <Route path="/kb/:id/confluence" element={<ConfluenceSpaces />} />
              <Route path="/settings" element={<Settings />} />
            </Routes>
          </main>
        </div>
        <Toaster />
      </div>
    </MotionConfig>
  )
}
