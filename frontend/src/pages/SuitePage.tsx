import { useCallback, useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { listRegulators } from '../api/snapshots'
import {
  attachFactFile,
  createRun,
  executeRun,
  getConfig,
  listEntities,
  listModuleVersions,
  runHistory,
  type Entity,
  type ModuleVersionOption,
  type Run,
  type WorkflowConfig,
} from '../api/workflows'
import RunStatusBadge from '../components/RunStatusBadge'
import UploadZone from '../components/UploadZone'
import {
  Block,
  ErrorText,
  FieldLabel,
  PageHeader,
  Select,
  SectionLabel,
  fieldClass,
  primaryBtn,
  secondaryBtn,
} from '../components/ui'
import { formatDate } from '../lib/format'
import { usePrimaryRegulator } from '../lib/useRegulator'

export default function SuitePage() {
  const { workflowId } = useParams()
  const id = Number(workflowId)
  const navigate = useNavigate()

  const [config, setConfig] = useState<WorkflowConfig | null>(null)
  const [regName, setRegName] = useState('')
  // Taxonomy versions available for this suite's module (deduped across
  // releases). Null while loading, so we can show a loading vs empty state.
  const [versions, setVersions] = useState<ModuleVersionOption[] | null>(null)
  const [entities, setEntities] = useState<Entity[]>([])
  const [runs, setRuns] = useState<Run[]>([])
  const [creating, setCreating] = useState(false)

  // Create form
  const [reportingDate, setReportingDate] = useState('')
  const [entityId, setEntityId] = useState<number | ''>('')
  const [snapshotKey, setSnapshotKey] = useState('')
  const [adjustedKey, setAdjustedKey] = useState('')
  const [versionKey, setVersionKey] = useState('')
  // Index into `versions` — nothing preselected; the user chooses deliberately.
  const [versionIdx, setVersionIdx] = useState<number | ''>('')
  const [factFile, setFactFile] = useState<File | null>(null)

  const [busy, setBusy] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [selectedDate, setSelectedDate] = useState<string | null>(null)

  const regCode = usePrimaryRegulator()?.code ?? ''

  const loadRuns = useCallback(() => {
    if (id) runHistory(id).then(setRuns).catch(() => setRuns([]))
  }, [id])

  useEffect(() => {
    getConfig(id).then(setConfig)
    listRegulators().then((rs) => setRegName(rs[0]?.name ?? '')).catch(() => {})
    listModuleVersions(id)
      .then((r) => setVersions(r.options))
      .catch(() => setVersions([]))
    listEntities().then(setEntities).catch(() => setEntities([]))
    loadRuns()
  }, [id, loadRuns])

  const selectedVersion =
    versionIdx !== '' && versions ? (versions[versionIdx] ?? null) : null

  const byDate = useMemo(() => {
    const m = new Map<string, Run[]>()
    for (const r of runs) {
      const arr = m.get(r.reference_date)
      if (arr) arr.push(r)
      else m.set(r.reference_date, [r])
    }
    return m
  }, [runs])
  const dates = useMemo(
    () => [...byDate.keys()].sort((a, b) => b.localeCompare(a)),
    [byDate],
  )
  useEffect(() => {
    if (dates.length && (selectedDate === null || !byDate.has(selectedDate))) {
      setSelectedDate(dates[0])
    }
  }, [dates, byDate, selectedDate])

  // A date's runs grouped into instances (by the three keys); latest prominent.
  const instances = useMemo(() => {
    const dateRuns = selectedDate ? (byDate.get(selectedDate) ?? []) : []
    const m = new Map<string, Run[]>()
    for (const r of dateRuns) {
      const sig = `${r.snapshot_key}|${r.adjusted_key}|${r.version_key}`
      const arr = m.get(sig)
      if (arr) arr.push(r)
      else m.set(sig, [r])
    }
    return [...m.values()].map((rs) => {
      const sorted = [...rs].sort((a, b) => b.id - a.id)
      return { latest: sorted[0], count: rs.length }
    })
  }, [byDate, selectedDate])

  const ready =
    reportingDate !== '' &&
    entityId !== '' &&
    selectedVersion !== null &&
    factFile !== null &&
    busy === null

  // The chosen version may not apply to the reporting date. ISO dates compare
  // correctly as strings. Informational only — never blocks — but never silent.
  const windowWarning = useMemo(() => {
    if (!selectedVersion || reportingDate === '') return null
    const { valid_from, valid_to } = selectedVersion
    if (valid_from && reportingDate < valid_from) {
      return `This version applies from ${formatDate(valid_from)} — your reporting date is ${formatDate(reportingDate)}.`
    }
    if (valid_to && reportingDate > valid_to) {
      return `This version applies until ${formatDate(valid_to)} — your reporting date is ${formatDate(reportingDate)}.`
    }
    return null
  }, [selectedVersion, reportingDate])

  async function handleExecute() {
    if (entityId === '' || selectedVersion === null || !factFile) return
    setError(null)
    try {
      setBusy('Creating submission…')
      const run = await createRun({
        workflow_id: id,
        // The chosen version resolves to the release providing it.
        snapshot_id: selectedVersion.snapshot_id,
        reference_date: reportingDate,
        entity_id: entityId,
        snapshot_key: snapshotKey || undefined,
        adjusted_key: adjustedKey || undefined,
        version_key: versionKey || undefined,
      })
      setBusy('Uploading facts…')
      await attachFactFile(run.id, factFile)
      setBusy('Generating and validating…')
      await executeRun(run.id)
      navigate(`/reporting/runs/${run.id}`)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setBusy(null)
      loadRuns()
    }
  }

  const category = config?.category ?? 'Reporting'

  return (
    <section>
      <PageHeader
        title={config?.name ?? 'Suite'}
        crumbs={[
          { label: 'Reporting', to: '/reporting' },
          ...(regCode ? [{ label: regName || regCode, to: `/reporting/${regCode}` }] : []),
          {
            label: category,
            to: regCode
              ? `/reporting/${regCode}/${encodeURIComponent(category)}`
              : '/reporting',
          },
          { label: config?.name ?? '' },
        ]}
        actions={
          !creating && (
            <button type="button" className={primaryBtn} onClick={() => setCreating(true)}>
              New submission
            </button>
          )
        }
      />

      {/* New submission — inline create form (no separate screen) */}
      {creating && (
        <div className="mb-10">
          <SectionLabel>New submission</SectionLabel>
          <Block className="p-6">
            {versions === null ? (
              <p className="text-[14px] text-sub">Loading taxonomy versions…</p>
            ) : versions.length === 0 ? (
              <p className="text-[14px] text-sub">
                No taxonomy version is available for this suite yet. Add a
                release that contains this module under Taxonomies before
                submitting.
              </p>
            ) : (
              <div className="space-y-5">
                <div className="grid gap-5 sm:grid-cols-2">
                  <label className="block">
                    <FieldLabel>Reporting date</FieldLabel>
                    <input
                      type="date"
                      className={fieldClass}
                      value={reportingDate}
                      onChange={(e) => setReportingDate(e.target.value)}
                    />
                  </label>
                  <label className="block">
                    <FieldLabel>Entity</FieldLabel>
                    <Select value={entityId} onChange={(v) => setEntityId(v === '' ? '' : Number(v))}>
                      <option value="">Select…</option>
                      {entities.map((en) => (
                        <option key={en.id} value={en.id}>
                          {en.name} · {en.lei}
                        </option>
                      ))}
                    </Select>
                  </label>
                </div>

                <div>
                  <FieldLabel>Instance keys</FieldLabel>
                  <div className="grid gap-4 sm:grid-cols-3">
                    {([
                      ['Snapshot', snapshotKey, setSnapshotKey],
                      ['Adjusted', adjustedKey, setAdjustedKey],
                      ['Version', versionKey, setVersionKey],
                    ] as const).map(([label, value, set]) => (
                      <input
                        key={label}
                        type="text"
                        aria-label={label}
                        placeholder={label}
                        className={`${fieldClass} font-mono`}
                        value={value}
                        onChange={(e) => set(e.target.value)}
                      />
                    ))}
                  </div>
                </div>

                <div className="grid gap-5 sm:grid-cols-2">
                  <label className="block">
                    <FieldLabel>Taxonomy version</FieldLabel>
                    <Select
                      value={versionIdx}
                      onChange={(v) => setVersionIdx(v === '' ? '' : Number(v))}
                    >
                      <option value="">Select…</option>
                      {/* Lead with the taxonomy version(s) — the release labels
                          the user recognises. Multiple providers show all. */}
                      {versions.map((o, i) => (
                        <option key={`${o.module_version}-${o.framework_version}`} value={i}>
                          {o.taxonomy_versions.join(', ')}
                        </option>
                      ))}
                    </Select>
                    {/* Module version + validity are supporting detail beneath. */}
                    {selectedVersion && (
                      <p className="mt-1.5 text-[12px] leading-snug text-sub">
                        Module version {selectedVersion.module_version}
                        {selectedVersion.valid_from &&
                          ` · applies from ${formatDate(selectedVersion.valid_from)}`}
                        {selectedVersion.valid_to &&
                          ` to ${formatDate(selectedVersion.valid_to)}`}
                      </p>
                    )}
                    {windowWarning && (
                      <p className="mt-1.5 flex items-start gap-1.5 text-[12px] leading-snug text-red">
                        <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-red" />
                        {windowWarning}
                      </p>
                    )}
                  </label>
                  <div className="block">
                    <FieldLabel>Fact file</FieldLabel>
                    <UploadZone accept=".xlsx" onFile={setFactFile} file={factFile} hint="XLSX" compact />
                  </div>
                </div>

                <div className="flex items-center gap-4 pt-1">
                  <button type="button" onClick={() => void handleExecute()} disabled={!ready} className={primaryBtn}>
                    Execute
                  </button>
                  <button
                    type="button"
                    className={secondaryBtn}
                    disabled={busy !== null}
                    onClick={() => setCreating(false)}
                  >
                    Cancel
                  </button>
                  {busy && <span className="text-[13px] text-sub">{busy}</span>}
                  <ErrorText>{error}</ErrorText>
                </div>
              </div>
            )}
          </Block>
        </div>
      )}

      {/* Submissions — by reporting date */}
      {dates.length > 0 && (
        <div className="flex gap-8">
          <div className="w-40 shrink-0">
            <SectionLabel>Reporting date</SectionLabel>
            <div className="space-y-1">
              {dates.map((d) => (
                <button
                  key={d}
                  type="button"
                  onClick={() => setSelectedDate(d)}
                  className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left font-mono text-[13px] transition-colors ${
                    selectedDate === d
                      ? 'bg-ink text-white'
                      : 'text-data hover:bg-hover'
                  }`}
                >
                  {formatDate(d)}
                </button>
              ))}
            </div>
          </div>

          <div className="min-w-0 flex-1">
            <SectionLabel>Submissions</SectionLabel>
            <Block className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="text-left text-[11px] font-bold uppercase tracking-[0.12em] text-muted">
                    <th className="px-6 py-3 font-bold">Snapshot</th>
                    <th className="px-6 py-3 font-bold">Adjusted</th>
                    <th className="px-6 py-3 font-bold">Version</th>
                    <th className="px-6 py-3 font-bold">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {instances.map(({ latest, count }) => (
                    <tr
                      key={latest.id}
                      onClick={() => navigate(`/reporting/runs/${latest.id}`)}
                      className="cursor-pointer border-t border-divider transition-colors hover:bg-hover"
                    >
                      <td className="px-6 py-[18px] font-mono text-[13px] text-data">{latest.snapshot_key}</td>
                      <td className="px-6 py-[18px] font-mono text-[13px] text-data">{latest.adjusted_key}</td>
                      <td className="px-6 py-[18px] font-mono text-[13px] text-data">{latest.version_key}</td>
                      <td className="px-6 py-[18px]">
                        <div className="flex items-center gap-3">
                          <RunStatusBadge status={latest.status} />
                          {count > 1 && (
                            <span className="text-[12px] text-muted">
                              {count} executions
                            </span>
                          )}
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </Block>
          </div>
        </div>
      )}
    </section>
  )
}
