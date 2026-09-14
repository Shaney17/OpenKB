import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Plus, FileText, Library, RefreshCw } from 'lucide-react'
import { listKbs, type KbSummary } from '@/api/kb'
import CreateKbDialog from '@/components/CreateKbDialog'
import { cn } from '@/lib/utils'

/** Decorative accent colors, cycled by position — the API carries no color. */
const DOTS = ['bg-blue-500', 'bg-emerald-500', 'bg-amber-500', 'bg-violet-500', 'bg-rose-500']
const dotFor = (i: number) => DOTS[i % DOTS.length]

export default function KbList() {
  const { t } = useTranslation(['kbList', 'common'])
  const navigate = useNavigate()
  const [kbs, setKbs] = useState<KbSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Date formatting stays a runtime value; only the surrounding copy is i18n'd.
  const formatCompile = (last: string | null): string =>
    last ? t('updatedAt', { date: last.replace('T', ' ').slice(0, 16) }) : t('notCompiled')

  useEffect(() => {
    let cancelled = false
    listKbs()
      .then(r => {
        if (cancelled) return
        setKbs(Array.isArray(r.knowledge_bases) ? r.knowledge_bases : [])
        setError(null)
      })
      .catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : String(e)) })
      .finally(() => { if (!cancelled) setLoading(false) })
    return () => { cancelled = true }
  }, [])

  return (
    <div className="h-full overflow-y-auto">
      <div className="max-w-screen-xl mx-auto px-6 lg:px-8 py-8">
        {/* pr-28 reserves the global top-right chrome lane (theme pill + future
            i18n switcher, see App.tsx) so 新建知识库 never sits under the pill.
            Only this control row reserves — the card grid below keeps full width. */}
        <div className="flex items-end justify-between anim-fade-up pr-28">
          <div>
            <h1 className="text-[22px] font-extrabold tracking-tight text-foreground">{t('title')}</h1>
            <p className="mt-1 text-[13px] text-muted-foreground">{t('subtitle')}</p>
          </div>
          <CreateKbDialog>
            <button className="inline-flex items-center gap-1.5 h-9 px-4 rounded-xl bg-accent-brand text-white text-[13px] font-medium hover:opacity-90 shadow-sm transition duration-fast ease-out-apple active:scale-[0.97]">
              <Plus className="w-4 h-4" />{t('common:actions.newKb')}
            </button>
          </CreateKbDialog>
        </div>

        {loading ? <p className="mt-12 text-sm text-muted-foreground">{t('common:loading')}</p>
          : error ? <div role="alert" className="mt-12 max-w-lg rounded-xl border border-red-200/70 bg-red-50 px-4 py-3 text-sm text-red-700 dark:border-red-500/25 dark:bg-red-500/10 dark:text-red-300">
            {t('loadError', { error })} <button className="ml-2 inline-flex items-center gap-1 font-semibold underline underline-offset-2" onClick={() => window.location.reload()}><RefreshCw className="size-3.5" />{t('retry')}</button>
          </div>
          : kbs.length === 0 ? <div className="mx-auto mt-20 max-w-md text-center">
            <Library className="mx-auto size-9 text-muted-foreground" />
            <h2 className="mt-4 text-lg font-bold">{t('empty.title')}</h2>
            <p className="mt-2 text-sm text-muted-foreground">{t('empty.description')}</p>
            <CreateKbDialog><button className="mt-5 inline-flex h-9 items-center gap-1.5 rounded-xl bg-accent-brand px-4 text-[13px] font-medium text-white hover:opacity-90"><Plus className="size-4" />{t('common:actions.newKb')}</button></CreateKbDialog>
          </div>
          : <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4">
          {kbs.map((kb, i) => (
            <button
              key={kb.name}
              onClick={() => navigate(`/kb/${encodeURIComponent(kb.name)}`)}
              className={cn('anim-fade-up text-left rounded-2xl border border-[hsl(var(--glass-border))] glass-2 p-5 hover:shadow-glass hover:-translate-y-0.5 transition-[transform,box-shadow] duration-fast ease-out-apple active:scale-[0.98]', `anim-d${(i % 4) + 1}`)}
            >
              <div className="flex items-center gap-2.5">
                <span className={cn('w-2.5 h-2.5 rounded-full', dotFor(i))} />
                <span className="text-[16px] font-bold text-foreground">{kb.name}</span>
              </div>

              {/* Directory in small muted mono so scattered (custom-path) KBs
                  stay legible. `title` exposes the full path when truncated. */}
              {kb.path && (
                <div className="mt-1.5 text-[11px] text-muted-foreground font-mono2 truncate" title={kb.path}>
                  {kb.path}
                </div>
              )}

              <div className="mt-4">
                <div className="inline-flex items-center gap-3 rounded-xl bg-muted/50 border border-[hsl(var(--glass-border))] px-3.5 py-2.5">
                  <FileText className="w-4 h-4 text-muted-foreground" />
                  <div>
                    <div className="text-[17px] font-bold text-foreground leading-none tabular-nums tracking-[-0.02em]">{kb.document_count}</div>
                    <div className="mt-1 text-[11px] text-muted-foreground">{t('docsLabel')}</div>
                  </div>
                </div>
              </div>

              <div className="mt-4 flex items-center justify-between text-[11.5px] text-muted-foreground">
                <span className={cn('font-mono2 rounded px-1.5 py-0.5', kb.has_raw ? 'bg-muted' : 'bg-amber-50 dark:bg-amber-500/10 text-amber-600 dark:text-amber-400')}>
                  {kb.has_raw ? t('rawReady') : t('rawMissing')}
                </span>
                <span>{formatCompile(kb.last_compile)}</span>
              </div>
            </button>
          ))}
        </div>}
      </div>
    </div>
  )
}
