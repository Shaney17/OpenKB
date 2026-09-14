import { Component, useCallback, useEffect, useMemo, useState, type ReactNode } from 'react'
import { useNavigate, useParams } from 'react-router'
import { useTranslation } from 'react-i18next'
import { ArrowLeft, BookOpen, CheckCircle2, Database, Loader2, Plus, RefreshCw, Search, Trash2, XCircle } from 'lucide-react'
import { toast } from 'sonner'
import { addConfluenceSpace, getConfluenceProject, removeConfluenceSpace, syncAllConfluenceSpaces, syncConfluenceSpace, type ConfluenceProject, type ConfluenceSpace } from '@/api/confluence'
import { Button } from '@/components/ui/button'
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { cn } from '@/lib/utils'

const message = (error: unknown) => error instanceof Error ? error.message : String(error)
class PageErrorBoundary extends Component<{ fallback: ReactNode; children: ReactNode }, { failed: boolean }> {
  state = { failed: false }
  static getDerivedStateFromError() { return { failed: true } }
  render() { return this.state.failed ? this.props.fallback : this.props.children }
}

function Status({ space }: { space: ConfluenceSpace }) {
  const { t } = useTranslation('confluence')
  const styles = {
    idle: 'text-muted-foreground bg-muted',
    running: 'text-blue-700 bg-blue-100 dark:text-blue-300 dark:bg-blue-500/15',
    succeeded: 'text-emerald-700 bg-emerald-100 dark:text-emerald-300 dark:bg-emerald-500/15',
    partial: 'text-amber-700 bg-amber-100 dark:text-amber-300 dark:bg-amber-500/15',
    failed: 'text-red-700 bg-red-100 dark:text-red-300 dark:bg-red-500/15',
  }
  return <span className={cn('inline-flex items-center gap-1.5 rounded-full px-2 py-1 text-[11px] font-semibold', styles[space.status])}>
    {space.status === 'running' ? <Loader2 className="size-3 animate-spin" /> : space.status === 'failed' ? <XCircle className="size-3" /> : <CheckCircle2 className="size-3" />}
    {t(`status.${space.status}`)}
  </span>
}

function AddDialog({ open, onOpenChange, project, onAdded }: { open: boolean; onOpenChange: (v: boolean) => void; project: string; onAdded: () => void }) {
  const { t } = useTranslation('confluence')
  const [spaceId, setSpaceId] = useState('')
  const [saving, setSaving] = useState(false)
  const submit = async (event: React.FormEvent) => {
    event.preventDefault(); setSaving(true)
    try {
      await addConfluenceSpace({ project, space_id: spaceId })
      toast.success(t('toast.added', { key: spaceId })); setSpaceId(''); onOpenChange(false); onAdded()
    } catch (error) { toast.error(message(error)) } finally { setSaving(false) }
  }
  return <Dialog open={open} onOpenChange={onOpenChange}><DialogContent>
    <DialogHeader><DialogTitle>{t('add.title')}</DialogTitle><DialogDescription>{t('add.description')}</DialogDescription></DialogHeader>
    <form onSubmit={submit} className="space-y-3">
      <label className="block text-[12px] font-medium">{t('add.id')}<Input required value={spaceId} onChange={e => setSpaceId(e.target.value)} placeholder="123456" className="mt-1.5" /></label>
      <DialogFooter><Button type="submit" disabled={saving}>{saving && <Loader2 className="animate-spin" />}{t('add.submit')}</Button></DialogFooter>
    </form>
  </DialogContent></Dialog>
}

function ConfluenceSpacesContent() {
  const { id = '' } = useParams(); const navigate = useNavigate(); const { t } = useTranslation('confluence')
  const [data, setData] = useState<ConfluenceProject | null>(null); const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [selected, setSelected] = useState<string | null>(null); const [adding, setAdding] = useState(false); const [filter, setFilter] = useState(''); const [syncingAll, setSyncingAll] = useState(false)
  const load = useCallback(async () => { try {
    const response = await getConfluenceProject(id)
    const next = response
    setData(next); setError(null); setSelected(current => current && next.spaces.some(s => s.ref === current) ? current : next.spaces[0]?.ref ?? null)
  } catch (e) { setError(message(e)) } finally { setLoading(false) } }, [id])
  useEffect(() => { const timer = window.setTimeout(() => void load(), 0); return () => window.clearTimeout(timer) }, [load])
  useEffect(() => { if (!data?.spaces.some(s => s.status === 'running')) return; const timer = window.setInterval(() => void load(), 1800); return () => window.clearInterval(timer) }, [data, load])
  const shown = useMemo(() => data?.spaces.filter(s => `${s.key} ${s.label}`.toLowerCase().includes(filter.toLowerCase())) ?? [], [data, filter])
  const active = data?.spaces.find(s => s.ref === selected) ?? null
  const sync = async (ref: string) => { try { await syncConfluenceSpace(id, ref); await load() } catch (e) { toast.error(message(e)) } }
  const syncAll = async () => { setSyncingAll(true); try { await syncAllConfluenceSpaces(id); await load(); toast.success(t('toast.syncAll')) } catch (e) { toast.error(message(e)) } finally { setSyncingAll(false) } }
  const remove = async (ref: string, key: string) => { if (!window.confirm(t('removeConfirm', { key }))) return; try { await removeConfluenceSpace(id, ref); toast.success(t('toast.removed', { key })); await load() } catch (e) { toast.error(message(e)) } }
  return <div className="h-full overflow-y-auto scroll-edge-top">
    <div className="mx-auto max-w-[1280px] px-5 pb-6 pt-16 md:py-6 lg:px-10">
      <div className="flex flex-wrap items-start gap-3 md:flex-nowrap md:pr-28">
        <Button variant="ghost" size="icon" onClick={() => navigate(`/kb/${encodeURIComponent(id)}`)} aria-label={t('back')}><ArrowLeft /></Button>
        <div><h1 className="text-[22px] font-extrabold tracking-tight">{t('title')}</h1><p className="mt-1 max-w-[68ch] text-[13px] text-muted-foreground">{t('subtitle', { project: id })}</p></div>
        <div className="grid w-full grid-cols-2 gap-2 md:ml-auto md:flex md:w-auto"><Button variant="outline" disabled={!data?.spaces.length || !data.connection.configured || !data.connection.token_configured || data.spaces.some(s => s.status === 'running')} onClick={() => void syncAll()}>{syncingAll ? <Loader2 className="animate-spin" /> : <RefreshCw />}{t('syncAll')}</Button><Button onClick={() => setAdding(true)}><Plus />{t('addSpace')}</Button></div>
      </div>
      {error && <div role="alert" className="mt-5 flex flex-col items-start gap-3 rounded-xl bg-red-50 px-4 py-3 text-[13px] text-red-700 dark:bg-red-500/10 dark:text-red-300 sm:flex-row sm:items-center"><span className="min-w-0 break-words">{error}</span><Button size="sm" variant="outline" className="shrink-0" onClick={() => void load()}><RefreshCw />{t('retry')}</Button></div>}
      {!data ? loading ? <div className="mt-10 flex items-center gap-2 text-sm text-muted-foreground"><Loader2 className="animate-spin" />{t('loading')}</div> : null : <>
        <div className="mt-6 flex flex-wrap items-center gap-x-6 gap-y-2 border-y border-[hsl(var(--glass-border))] py-3 text-[12px] text-muted-foreground">
          <span><strong className="text-foreground">{data.spaces.length}</strong> {t('spaces')}</span><span>{data.connection.base_url || t('notConfigured')}</span>{data.connection.email && <span>{data.connection.email}</span>}<span className={data.connection.token_configured ? 'text-emerald-600 dark:text-emerald-400' : 'text-amber-600 dark:text-amber-400'}>{data.connection.token_configured ? t('tokenReady') : t('tokenMissing')}</span>
        </div>
        {data.spaces.length === 0 ? <div className="mx-auto mt-20 max-w-md text-center"><Database className="mx-auto size-9 text-muted-foreground" /><h2 className="mt-4 text-lg font-bold">{t('empty.title')}</h2><p className="mt-2 text-sm text-muted-foreground">{t('empty.description')}</p><Button className="mt-5" onClick={() => setAdding(true)}><Plus />{t('addSpace')}</Button></div> : <div className="mt-5 grid min-h-[560px] grid-cols-1 overflow-hidden rounded-2xl border border-[hsl(var(--glass-border))] bg-background/55 lg:grid-cols-[340px_1fr]">
          <section className="border-b border-[hsl(var(--glass-border))] lg:border-b-0 lg:border-r">
            <div className="relative m-3"><Search className="absolute left-3 top-2.5 size-4 text-muted-foreground" /><Input value={filter} onChange={e => setFilter(e.target.value)} placeholder={t('search')} className="pl-9" /></div>
            <div className="max-h-[520px] overflow-y-auto">{shown.map(space => <button key={space.ref} onClick={() => setSelected(space.ref)} className={cn('w-full border-t border-[hsl(var(--glass-border))] px-4 py-3 text-left transition-colors hover:bg-accent/50', selected === space.ref && 'bg-accent/70')}>
              <div className="flex items-center gap-2"><span className="font-bold">{space.label}</span><span className="ml-auto font-mono2 text-[11px] text-muted-foreground">{space.key}</span></div><div className="mt-2 flex items-center justify-between"><Status space={space} /><span className="text-[11px] tabular-nums text-muted-foreground">{space.inventory?.document_count ?? 0} {t('pages')}</span></div>
            </button>)}</div>
          </section>
          <section className="p-5 lg:p-7">{active && <>
            <div className="flex flex-wrap items-start gap-3"><div><h2 className="text-xl font-extrabold tracking-tight">{active.label}</h2><p className="mt-1 text-[12px] text-muted-foreground">{active.key} · ID {active.confluence_id || active.ref} · {active.last_finished_at ? new Date(active.last_finished_at).toLocaleString() : t('neverSynced')}</p></div><div className="ml-auto flex gap-2"><Button variant="outline" size="sm" onClick={() => void remove(active.ref, active.key)}><Trash2 />{t('remove')}</Button><Button size="sm" disabled={active.status === 'running' || !data.connection.configured || !data.connection.token_configured} onClick={() => void sync(active.ref)}>{active.status === 'running' ? <Loader2 className="animate-spin" /> : <RefreshCw />}{t('sync')}</Button></div></div>
            {active.error && <p className="mt-4 rounded-xl bg-red-50 px-3 py-2 text-[12px] text-red-700 dark:bg-red-500/10 dark:text-red-300">{active.error}</p>}
            {active.last_result && <p className="mt-3 text-[12px] text-muted-foreground">{t('result', { discovered: active.last_result.discovered ?? 0, added: active.last_result.added ?? 0, updated: active.last_result.updated ?? 0, unchanged: active.last_result.unchanged ?? 0, failed: active.last_result.failed ?? 0 })}</p>}
            <div className="mt-7 grid grid-cols-2 gap-px overflow-hidden rounded-xl bg-[hsl(var(--glass-border))] sm:grid-cols-4">{(['concepts','entities','summaries','documents'] as const).map(group => <div key={group} className="bg-background/95 px-4 py-3"><div className="text-[11px] text-muted-foreground">{t(`inventory.${group}`)}</div><div className="mt-1 text-2xl font-bold tabular-nums">{group === 'documents' ? active.inventory?.document_count ?? 0 : active.inventory?.[group]?.length ?? 0}</div></div>)}</div>
            <div className="mt-7 grid gap-6 md:grid-cols-2">{(['concepts','entities','summaries'] as const).map(group => <div key={group}><h3 className="flex items-center gap-2 text-[13px] font-bold"><BookOpen className="size-4 text-accent-brand" />{t(`inventory.${group}`)}</h3><div className="mt-2 max-h-44 overflow-y-auto rounded-xl bg-muted/45 px-3 py-2">{active.inventory?.[group]?.length ? active.inventory[group].map(name => <div key={name} className="border-b border-[hsl(var(--glass-border))] py-1.5 text-[12px] last:border-0">{name}</div>) : <p className="py-2 text-[12px] text-muted-foreground">{t('inventory.empty')}</p>}</div></div>)}</div>
          </>}</section>
        </div>}
      </>}
    </div>{adding && <AddDialog open={adding} onOpenChange={setAdding} project={id} onAdded={() => void load()} />}
  </div>
}

export default function ConfluenceSpaces() {
  const { id = '' } = useParams()
  const navigate = useNavigate()
  const { t } = useTranslation('confluence')
  const fallback = <div className="flex h-full items-center justify-center px-6">
    <div className="max-w-md text-center">
      <XCircle className="mx-auto size-9 text-red-600 dark:text-red-400" />
      <h1 className="mt-4 text-lg font-bold">{t('renderError.title')}</h1>
      <p className="mt-2 text-sm text-muted-foreground">{t('renderError.description')}</p>
      <div className="mt-5 flex justify-center gap-2"><Button variant="outline" onClick={() => navigate(`/kb/${encodeURIComponent(id)}`)}><ArrowLeft />{t('back')}</Button><Button onClick={() => window.location.reload()}><RefreshCw />{t('renderError.reload')}</Button></div>
    </div>
  </div>
  return <PageErrorBoundary key={id} fallback={fallback}><ConfluenceSpacesContent /></PageErrorBoundary>
}
