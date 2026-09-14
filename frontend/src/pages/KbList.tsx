import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { useTranslation } from 'react-i18next'
import { Plus, FileText, Library, RefreshCw, ArrowRight, Cloud, Folder } from 'lucide-react'
import { listKbs, type KbSummary } from '@/api/kb'
import CreateKbDialog from '@/components/CreateKbDialog'
import { cn } from '@/lib/utils'

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
          : <div className="mt-6 overflow-hidden rounded-2xl border border-[hsl(var(--glass-border))] bg-background/55">
          <div className="hidden grid-cols-[minmax(0,2fr)_minmax(130px,1.2fr)_minmax(120px,1fr)_85px] gap-4 border-b border-[hsl(var(--glass-border))] bg-muted/25 px-5 py-3 text-[11px] font-bold uppercase tracking-wider text-muted-foreground md:grid">
            <span>{t('columns.kb')}</span><span>{t('columns.source')}</span><span>{t('columns.status')}</span><span>{t('columns.docs')}</span>
          </div>
          {kbs.map((kb) => (
            <button
              key={kb.name}
              onClick={() => navigate(`/kb/${encodeURIComponent(kb.name)}`)}
              className="group grid w-full gap-3 border-b border-[hsl(var(--glass-border))] px-5 py-4 text-left last:border-0 hover:bg-accent/50 md:grid-cols-[minmax(0,2fr)_minmax(130px,1.2fr)_minmax(120px,1fr)_85px] md:items-center md:gap-4"
            >
              <div className="min-w-0">
                <div className="flex items-center gap-2.5"><Library className="size-4 shrink-0 text-accent-brand" /><span className="truncate text-[14px] font-bold">{kb.name}</span><ArrowRight className="size-3.5 text-muted-foreground opacity-0 group-hover:opacity-100" /></div>
                <div className="mt-1.5 truncate pl-[26px] text-[11px] text-muted-foreground" title={kb.path}>{formatCompile(kb.last_compile)}</div>
              </div>
              <div className="min-w-0 text-[12px] text-muted-foreground" title={kb.source_labels.join(', ')}>
                <div className="flex items-center gap-2">
                  {kb.source_type === 'confluence' ? <Cloud className="size-4 shrink-0" /> : <Folder className="size-4 shrink-0" />}
                  <span>{kb.source_type === 'confluence' ? t('confluenceSpaces', { count: kb.space_count }) : t('localFiles')}</span>
                </div>
                {kb.source_labels.length > 0 && <div className="mt-1 truncate pl-6 text-[11px]">{kb.source_labels.join(', ')}</div>}
              </div>
              <div>
                <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-medium',
                  kb.sync_status === 'succeeded' ? 'bg-emerald-500/10 text-emerald-600 dark:text-emerald-400' :
                  kb.sync_status === 'running' ? 'bg-blue-500/10 text-blue-600 dark:text-blue-400' :
                  kb.sync_status === 'failed' || kb.sync_status === 'partial' ? 'bg-amber-500/10 text-amber-700 dark:text-amber-400' : 'bg-muted text-muted-foreground')}
                >
                  <span className={cn('size-1.5 rounded-full bg-current', kb.sync_status === 'running' && 'animate-pulse')} />
                  {kb.source_type === 'confluence' ? t(`syncStatus.${kb.sync_status ?? 'idle'}`) : t('localStatus')}
                </span>
              </div>
              <div className="flex items-center gap-1.5 text-[12px] tabular-nums text-muted-foreground"><FileText className="size-3.5" />{kb.document_count}</div>
            </button>
          ))}
        </div>}
      </div>
    </div>
  )
}
