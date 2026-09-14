import { apiFetch } from './client'
import type { KbInventory, WikiDocument } from './wiki'

export type SyncStatus = 'idle' | 'running' | 'succeeded' | 'partial' | 'failed'

export interface ConfluenceSpace {
  ref: string
  key: string
  confluence_id: string | null
  label: string
  status: SyncStatus
  created_at: string
  last_started_at: string | null
  last_finished_at: string | null
  last_result: Record<string, number> | null
  error: string | null
  failed_pages?: string[]
  inventory: KbInventory | null
}

export interface ConfluenceProject {
  connection: { base_url: string; email: string; token_configured: boolean; configured: boolean }
  spaces: ConfluenceSpace[]
}

const statuses = new Set<SyncStatus>(['idle', 'running', 'succeeded', 'partial', 'failed'])
const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === 'object' && !Array.isArray(value)
    ? value as Record<string, unknown>
    : {}
const text = (value: unknown): string =>
  typeof value === 'string' || typeof value === 'number' ? String(value) : ''
const count = (value: unknown): number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0
const names = (value: unknown): string[] =>
  Array.isArray(value)
    ? value.map(item => text(item) || text(record(item).name) || text(record(item).title)).filter(Boolean)
    : []

/** Older project records can contain partial fields and structured errors.
 * Normalize at the API boundary so one bad space cannot crash the whole page. */
export function normalizeConfluenceProject(value: unknown): ConfluenceProject {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) {
    throw new Error('Invalid Confluence project response')
  }
  const raw = record(value)
  const connection = record(raw.connection)
  const rawSpaces = Array.isArray(raw.spaces)
    ? raw.spaces
    : Object.entries(record(raw.spaces)).map(([ref, space]) => ({ ...record(space), ref }))
  const spaces = rawSpaces.flatMap((item): ConfluenceSpace[] => {
    const space = record(item)
    const ref = text(space.ref) || text(space.confluence_id) || text(space.key)
    if (!ref) return []
    const key = text(space.key) || ref
    const status = text(space.status) as SyncStatus
    const inventory = space.inventory === null || space.inventory === undefined
      ? null
      : record(space.inventory)
    const documents = Array.isArray(inventory?.documents)
      ? inventory.documents.filter((doc): doc is WikiDocument =>
          typeof record(doc).name === 'string' && typeof record(doc).hash === 'string')
      : []
    const error = text(space.error) || text(record(space.error).message) || null
    const result = record(space.last_result)
    return [{
      ref,
      key,
      confluence_id: text(space.confluence_id) || null,
      label: text(space.label) || key,
      status: statuses.has(status) ? status : 'idle',
      created_at: text(space.created_at),
      last_started_at: text(space.last_started_at) || null,
      last_finished_at: text(space.last_finished_at) || null,
      last_result: Object.keys(result).length ? Object.fromEntries(
        Object.entries(result).map(([field, number]) => [field, count(number)]),
      ) : null,
      error,
      failed_pages: names(space.failed_pages),
      inventory: inventory ? {
        documents,
        document_count: inventory.document_count === undefined
          ? documents.length
          : count(inventory.document_count),
        summaries: names(inventory.summaries),
        concepts: names(inventory.concepts),
        entities: names(inventory.entities),
        reports: names(inventory.reports),
      } : null,
    }]
  })
  return {
    connection: {
      base_url: text(connection.base_url),
      email: text(connection.email),
      token_configured: connection.token_configured === true,
      configured: connection.configured === true || (
        connection.configured === undefined && !!text(connection.base_url) && !!text(connection.email)
      ),
    },
    spaces,
  }
}

export function getConfluenceProject(project: string): Promise<ConfluenceProject> {
  return apiFetch<unknown>(`/api/v1/confluence/projects?project=${encodeURIComponent(project)}`)
    .then(normalizeConfluenceProject)
}

export function addConfluenceSpace(input: {
  project: string
  space_id: string
}): Promise<{ space: ConfluenceSpace }> {
  return apiFetch('/api/v1/confluence/spaces', { body: input })
}

export function removeConfluenceSpace(project: string, space_id: string): Promise<void> {
  return apiFetch('/api/v1/confluence/spaces', { method: 'DELETE', body: { project, space_id } })
}

export function syncConfluenceSpace(project: string, space_id: string): Promise<void> {
  return apiFetch('/api/v1/confluence/spaces/sync', { body: { project, space_id } })
}

export function syncAllConfluenceSpaces(project: string): Promise<void> {
  return apiFetch('/api/v1/confluence/spaces/sync-all', { body: { project } })
}
