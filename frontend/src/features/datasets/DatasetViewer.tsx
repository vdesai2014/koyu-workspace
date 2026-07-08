import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'

import { Button } from '../../components/ui/Button'
import {
  fetchDatasetEpisodeDetail,
  fetchDatasetEpisodesPage,
  fetchDatasetManifest,
  fetchDatasetManifestRuns,
  getEpisodeCameraList,
  getParquetUrl,
  patchEpisode,
  resolveEpisodeVideoUrl,
} from './api'
import { parseEpisodeParquet } from './parquet'
import { TimeSeriesPlot } from './TimeSeriesPlot'
import type {
  DatasetEpisodeDetail,
  DatasetEpisodePage,
  DatasetManifestDetail,
  DatasetManifestRunSummary,
  ParsedEpisodeData,
} from './types'

type LoadedEpisodePage = {
  cursor: string | null
  data: DatasetEpisodePage
}

const PAGE_SIZE_OPTIONS = [25, 50, 100]

function storageKey(manifestId: string) {
  return `viewer-state:${manifestId}`
}

function readStoredState(manifestId: string) {
  try {
    const raw = window.localStorage.getItem(storageKey(manifestId))
    if (!raw) return { lastEpisodeId: null as string | null, pageSize: 25 }
    const parsed = JSON.parse(raw) as { lastEpisodeId?: string | null; pageSize?: number }
    return {
      lastEpisodeId: parsed.lastEpisodeId ?? null,
      pageSize: PAGE_SIZE_OPTIONS.includes(parsed.pageSize ?? 0) ? (parsed.pageSize as number) : 25,
    }
  } catch {
    return { lastEpisodeId: null as string | null, pageSize: 25 }
  }
}

function writeStoredState(manifestId: string, lastEpisodeId: string | null, pageSize: number) {
  window.localStorage.setItem(storageKey(manifestId), JSON.stringify({ lastEpisodeId, pageSize }))
}

function formatPlaybackTime(totalSeconds: number) {
  if (!Number.isFinite(totalSeconds) || totalSeconds < 0) return '0:00.00'
  const mins = Math.floor(totalSeconds / 60)
  const secs = Math.floor(totalSeconds % 60)
  const cs = Math.floor((totalSeconds % 1) * 100)
  return `${mins}:${String(secs).padStart(2, '0')}.${String(cs).padStart(2, '0')}`
}

function formatEpisodeTimestamp(iso: string | null | undefined) {
  if (!iso) return 'unknown time'
  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return 'unknown time'
  const mm = String(date.getMonth() + 1).padStart(2, '0')
  const dd = String(date.getDate()).padStart(2, '0')
  const hh = String(date.getHours()).padStart(2, '0')
  const min = String(date.getMinutes()).padStart(2, '0')
  return `${mm}-${dd} ${hh}:${min}`
}

function CopyIdButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false)
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(value)
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1400)
    } catch {
      // clipboard can be denied in insecure contexts; title attribute still has the value
    }
  }
  return (
    <button
      type="button"
      className={`coupon-copy-btn${copied ? ' is-copied' : ''}`}
      onClick={handleCopy}
      title={value}
      aria-label={copied ? 'Copied' : 'Copy ID'}
    >
      {copied ? (
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M3 8l3 3 7-7" />
        </svg>
      ) : (
        <svg viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.3" strokeLinecap="round" strokeLinejoin="round">
          <rect x="5" y="5" width="8" height="9" rx="1" />
          <path d="M3 11V3a1 1 0 0 1 1-1h7" />
        </svg>
      )}
    </button>
  )
}

function LinkedRunsCarousel({
  runs,
  activeIndex,
  onPrevious,
  onNext,
}: {
  runs: DatasetManifestRunSummary[]
  activeIndex: number
  onPrevious: () => void
  onNext: () => void
}) {
  const boundedIndex = runs.length > 0 ? Math.min(activeIndex, runs.length - 1) : 0
  const activeRun = runs[boundedIndex] ?? null
  if (!activeRun) return null

  const hasMultiple = runs.length > 1
  return (
    <section className="coupon-linked-runs" aria-label="Linked runs">
      <button
        type="button"
        className="coupon-linked-run-nav"
        onClick={onPrevious}
        disabled={!hasMultiple}
        aria-label="Previous linked run"
        title="Previous linked run"
      >
        ‹
      </button>
      <Link
        className="coupon-linked-run-card"
        to={`/projects/${activeRun.project_id}/runs/${activeRun.id}`}
        title={activeRun.id}
      >
        <span className="coupon-linked-run-kicker">
          Linked run {boundedIndex + 1}/{runs.length}
        </span>
        <strong>{activeRun.name}</strong>
        <span className="coupon-linked-run-meta">
          <code>{activeRun.id.slice(0, 8)}</code>
          <span title={activeRun.project_id}>{activeRun.project_id}</span>
        </span>
      </Link>
      <button
        type="button"
        className="coupon-linked-run-nav"
        onClick={onNext}
        disabled={!hasMultiple}
        aria-label="Next linked run"
        title="Next linked run"
      >
        ›
      </button>
    </section>
  )
}

interface DatasetViewerProps {
  manifestId: string
  compact?: boolean
}

export function DatasetViewer({ manifestId, compact = false }: DatasetViewerProps) {
  // Read once per manifest, not on every render — otherwise the object identity
  // flips each time localStorage updates (on every episode click) and the boot
  // effect below re-fires, wiping pages + scroll position.
  const initialStored = useMemo(
    () => (manifestId
      ? readStoredState(manifestId)
      : { lastEpisodeId: null as string | null, pageSize: 25 }),
    [manifestId],
  )

  const [manifest, setManifest] = useState<DatasetManifestDetail | null>(null)
  const [linkedRuns, setLinkedRuns] = useState<DatasetManifestRunSummary[]>([])
  const [linkedRunsError, setLinkedRunsError] = useState<string | null>(null)
  const [activeLinkedRunIndex, setActiveLinkedRunIndex] = useState(0)
  const [pages, setPages] = useState<LoadedEpisodePage[]>([])
  const [pageIndex, setPageIndex] = useState(0)
  const [pageSize, setPageSize] = useState(initialStored.pageSize)
  const [selectedEpisodeId, setSelectedEpisodeId] = useState<string | null>(initialStored.lastEpisodeId)
  const [selectedEpisode, setSelectedEpisode] = useState<DatasetEpisodeDetail | null>(null)
  const [parsedData, setParsedData] = useState<ParsedEpisodeData | null>(null)
  const [loading, setLoading] = useState(true)
  const [loadingEpisode, setLoadingEpisode] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [currentFrame, setCurrentFrame] = useState(0)
  const [isPlaying, setIsPlaying] = useState(false)
  const [expandedCamera, setExpandedCamera] = useState<string | null>(null)
  const [toasts, setToasts] = useState<{ id: number; message: string; tone?: 'error' | 'info' }[]>([])
  const toastCounterRef = useRef(0)

  const notify = useCallback((message: string, tone: 'error' | 'info' = 'info') => {
    const id = ++toastCounterRef.current
    setToasts((prev) => [...prev, { id, message, tone }])
    window.setTimeout(() => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id))
    }, 3200)
  }, [])

  const videoRefs = useRef<Record<string, HTMLVideoElement | null>>({})

  const currentPage = pages[pageIndex]?.data ?? null
  const episodeSummaries = currentPage?.episodes ?? []
  const cameras = useMemo(() => getEpisodeCameraList(selectedEpisode), [selectedEpisode])
  const maxFrameIndex = useMemo(() => {
    if (parsedData?.frameIndices.length) {
      return Math.max(...parsedData.frameIndices)
    }
    return Math.max(0, (selectedEpisode?.length ?? 1) - 1)
  }, [parsedData?.frameIndices, selectedEpisode?.length])

  const loadPage = useCallback(async (cursor: string | null, targetIndex: number) => {
    const data = await fetchDatasetEpisodesPage(manifestId, pageSize, cursor)
    setPages((current) => {
      const next = [...current]
      next[targetIndex] = { cursor, data }
      return next
    })
    return data
  }, [manifestId, pageSize])

  useEffect(() => {
    if (!manifestId) return
    let cancelled = false

    async function boot() {
      setLoading(true)
      setError(null)
      setPages([])
      setPageIndex(0)
      setLinkedRuns([])
      setLinkedRunsError(null)
      setActiveLinkedRunIndex(0)
      setSelectedEpisode(null)
      setParsedData(null)
      try {
        const [manifestDetail, manifestRuns] = await Promise.all([
          fetchDatasetManifest(manifestId),
          fetchDatasetManifestRuns(manifestId)
            .then((response) => ({ runs: response.runs, error: null as string | null }))
            .catch((runError) => ({
              runs: [],
              error: (runError as Error).message || 'Linked run metadata is not available locally.',
            })),
        ])
        if (cancelled) return
        setManifest(manifestDetail)
        setLinkedRuns(manifestRuns.runs)
        setLinkedRunsError(manifestRuns.error)

        const firstPage = await fetchDatasetEpisodesPage(manifestId, pageSize, null)
        if (cancelled) return
        setPages([{ cursor: null, data: firstPage }])

        const desired = initialStored.lastEpisodeId
        const selected = firstPage.episodes.find((episode) => episode.id === desired)?.id
          ?? firstPage.episodes[0]?.id
          ?? null
        setSelectedEpisodeId(selected)
      } catch (err) {
        if (!cancelled) setError((err as Error).message || 'Failed to load dataset viewer')
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void boot()
    return () => {
      cancelled = true
    }
  }, [initialStored, manifestId, pageSize])

  useEffect(() => {
    if (!manifestId || !selectedEpisodeId) return
    const episodeId = selectedEpisodeId
    let cancelled = false
    setLoadingEpisode(true)
    setParsedData(null)
    setCurrentFrame(0)
    setIsPlaying(false)
    for (const video of Object.values(videoRefs.current)) {
      if (!video) continue
      video.pause()
      try {
        video.currentTime = 0
      } catch {
        // some browsers throw if metadata hasn't loaded yet; safe to ignore
      }
    }

    async function loadSelectedEpisode() {
      try {
        const detail = await fetchDatasetEpisodeDetail(manifestId, episodeId)
        if (cancelled) return
        setSelectedEpisode(detail)

        const parquetUrl = detail ? getParquetUrl(detail.files) : null
        if (!detail || !parquetUrl) {
          setParsedData(null)
          return
        }

        const parsed = await parseEpisodeParquet(parquetUrl, detail)
        if (cancelled) return
        setParsedData(parsed)
      } catch (err) {
        if (!cancelled) setError((err as Error).message || 'Failed to load episode')
      } finally {
        if (!cancelled) setLoadingEpisode(false)
      }
    }

    void loadSelectedEpisode()
    writeStoredState(manifestId, episodeId, pageSize)
    return () => {
      cancelled = true
    }
  }, [manifestId, pageSize, selectedEpisodeId])

  useEffect(() => {
    if (!currentPage || !selectedEpisodeId || loadingEpisode) return
    const idx = currentPage.episodes.findIndex((episode) => episode.id === selectedEpisodeId)
    const neighbor = currentPage.episodes[idx + 1]?.id
    if (!neighbor) return
    void fetchDatasetEpisodeDetail(manifestId, neighbor).catch(() => {})
  }, [currentPage, loadingEpisode, manifestId, selectedEpisodeId])

  useEffect(() => {
    setActiveLinkedRunIndex((current) => {
      if (linkedRuns.length === 0) return 0
      return Math.min(current, linkedRuns.length - 1)
    })
  }, [linkedRuns.length])

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setExpandedCamera(null)
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const handleLeaderTimeUpdate = useCallback(() => {
    const leader = cameras[0] ? videoRefs.current[cameras[0]] : null
    if (!leader) return
    const duration = leader.duration || 0
    const fraction = duration > 0 ? leader.currentTime / duration : 0
    setCurrentFrame(Math.round(Math.max(0, Math.min(1, fraction)) * maxFrameIndex))
    setIsPlaying(!leader.paused && !leader.ended)
  }, [cameras, maxFrameIndex])

  const handlePlayStateChange = useCallback(() => {
    const leader = cameras[0] ? videoRefs.current[cameras[0]] : null
    if (!leader) return
    setIsPlaying(!leader.paused && !leader.ended)
  }, [cameras])

  const togglePlay = useCallback(() => {
    const videos = cameras.map((camera) => videoRefs.current[camera]).filter(Boolean) as HTMLVideoElement[]
    if (!videos.length) return
    if (videos[0].paused) {
      void Promise.all(videos.map((video) => video.play().catch(() => undefined))).then(() => {
        const leader = videos[0]
        setIsPlaying(!leader.paused && !leader.ended)
      })
    } else {
      videos.forEach((video) => video.pause())
      setIsPlaying(false)
    }
  }, [cameras])

  const stepFrame = useCallback((delta: number) => {
    const leader = cameras[0] ? videoRefs.current[cameras[0]] : null
    const nextFrame = Math.max(0, Math.min(maxFrameIndex, currentFrame + delta))
    const duration = leader?.duration || 0
    const nextTime = maxFrameIndex > 0 ? duration * (nextFrame / maxFrameIndex) : 0
    cameras.forEach((camera) => {
      const video = videoRefs.current[camera]
      if (video) {
        video.pause()
        video.currentTime = nextTime
      }
    })
    setIsPlaying(false)
    setCurrentFrame(nextFrame)
  }, [cameras, currentFrame, maxFrameIndex])

  const scrubToFraction = useCallback((fraction: number) => {
    const leader = cameras[0] ? videoRefs.current[cameras[0]] : null
    if (!leader) return
    const nextTime = (leader.duration || 0) * fraction
    cameras.forEach((camera) => {
      const video = videoRefs.current[camera]
      if (video) {
        video.currentTime = nextTime
      }
    })
  }, [cameras])

  async function loadMore() {
    if (!currentPage?.next_cursor) return
    const nextIndex = pageIndex + 1
    if (!pages[nextIndex]) {
      await loadPage(currentPage.next_cursor, nextIndex)
    }
    setPageIndex(nextIndex)
  }

  function goPrevPage() {
    setPageIndex((current) => Math.max(0, current - 1))
  }

  function goPreviousLinkedRun() {
    setActiveLinkedRunIndex((current) => (
      linkedRuns.length ? (current - 1 + linkedRuns.length) % linkedRuns.length : 0
    ))
  }

  function goNextLinkedRun() {
    setActiveLinkedRunIndex((current) => (
      linkedRuns.length ? (current + 1) % linkedRuns.length : 0
    ))
  }

  const rateEpisode = useCallback(
    async (episodeId: string, current: number | null, value: number) => {
      const next = current === value ? null : value
      try {
        const updated = await patchEpisode(episodeId, { reward: next })
        setPages((prev) => prev.map((page) => ({
          ...page,
          data: {
            ...page.data,
            episodes: page.data.episodes.map((ep) =>
              ep.id === episodeId ? { ...ep, reward: updated.reward } : ep,
            ),
          },
        })))
        setSelectedEpisode((episode) => (
          episode?.id === episodeId ? { ...episode, reward: updated.reward } : episode
        ))
        // Refetch manifest to pick up recomputed success_rate + rated_episodes.
        // Fire-and-forget; the rollup is best-effort display.
        void fetchDatasetManifest(manifestId).then(setManifest).catch(() => {})
      } catch (err) {
        console.error('Failed to rate episode', err)
        notify((err as Error)?.message || 'Failed to rate episode', 'error')
      }
    },
    [manifestId, notify],
  )

  if (loading) {
    return <section className="projects-empty-state">Loading dataset…</section>
  }

  if (error || !manifest) {
    return <div className="projects-status projects-status-error">{error || 'Manifest not found.'}</div>
  }

  return (
    <div className={`coupon-shell${compact ? ' coupon-shell-compact' : ''}`}>
      {!compact ? (
        <header className="coupon-hero">
          <div>
            {manifest.description ? (
              <p className="project-hero-copy">{manifest.description}</p>
            ) : null}
          </div>
        </header>
      ) : null}

      <div className={`coupon-layout${compact ? ' coupon-layout-compact' : ''}`}>
        <aside className="coupon-episode-panel">
          <div className="coupon-episode-panel-head">
            <strong>Episodes</strong>
            <select value={pageSize} onChange={(event) => setPageSize(Number(event.target.value))}>
              {PAGE_SIZE_OPTIONS.map((option) => (
                <option key={option} value={option}>{option} / page</option>
              ))}
            </select>
          </div>
          <div className="coupon-episode-list">
            {episodeSummaries.map((episode) => {
              const isActive = episode.id === selectedEpisodeId
              const reward = episode.reward
              const rewardClass =
                reward === 1 ? ' is-success' : reward === 0 ? ' is-fail' : ''
              return (
                <div
                  key={episode.id}
                  role="button"
                  tabIndex={0}
                  className={`coupon-episode-item${isActive ? ' is-active' : ''}${rewardClass}`}
                  onClick={() => setSelectedEpisodeId(episode.id)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter' || event.key === ' ') {
                      event.preventDefault()
                      setSelectedEpisodeId(episode.id)
                    }
                  }}
                >
                  <div className="coupon-episode-item-rate" data-tour="thumbs">
                    <button
                      type="button"
                      data-tour="thumbs-up"
                      className={`coupon-rate-btn coupon-rate-up${reward === 1 ? ' is-active' : ''}`}
                      aria-label={reward === 1 ? 'Unrate episode' : 'Rate episode as success'}
                      onClick={(event) => {
                        event.stopPropagation()
                        void rateEpisode(episode.id, reward, 1)
                      }}
                    >
                      <svg viewBox="0 0 24 24" fill={reward === 1 ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round">
                        <path d="M14 9V5a3 3 0 0 0-3-3l-4 9v11h11.28a2 2 0 0 0 2-1.7l1.38-9a2 2 0 0 0-2-2.3H14zM7 22H4a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2h3" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      data-tour="thumbs-down"
                      className={`coupon-rate-btn coupon-rate-down${reward === 0 ? ' is-active' : ''}`}
                      aria-label={reward === 0 ? 'Unrate episode' : 'Rate episode as fail'}
                      onClick={(event) => {
                        event.stopPropagation()
                        void rateEpisode(episode.id, reward, 0)
                      }}
                    >
                      <svg viewBox="0 0 24 24" fill={reward === 0 ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinejoin="round" strokeLinecap="round">
                        <path d="M10 15v4a3 3 0 0 0 3 3l4-9V2H5.72a2 2 0 0 0-2 1.7l-1.38 9a2 2 0 0 0 2 2.3H10zM17 2h2.67A2.31 2.31 0 0 1 22 4v7a2.31 2.31 0 0 1-2.33 2H17" />
                      </svg>
                    </button>
                  </div>
                  <div className="coupon-episode-item-body">
                    <div className="coupon-episode-item-top">
                      <strong>{formatEpisodeTimestamp(episode.created_at)}</strong>
                      <span>{episode.length}f</span>
                    </div>
                    <div className="coupon-episode-item-meta">
                      <span>{episode.collection_mode ?? episode.task ?? 'unlabeled'}</span>
                      <span>{Object.keys(episode.features).filter((key) => key.includes('images')).length} cams</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
          <div className="coupon-episode-pagination">
            <Button type="button" variant="ghost" onClick={goPrevPage} disabled={pageIndex === 0}>
              Previous
            </Button>
            <span>Page {pageIndex + 1}</span>
            <Button type="button" variant="ghost" onClick={() => { void loadMore() }} disabled={!currentPage?.next_cursor}>
              Next
            </Button>
          </div>
        </aside>

        <main className="coupon-viewer">
          <div className="coupon-stage">
            <div
              className={`coupon-video-grid${expandedCamera ? ' has-expanded' : ''}`}
              data-cameras={cameras.length}
            >
              {cameras.map((camera) => {
                const videoUrl = selectedEpisode ? resolveEpisodeVideoUrl(selectedEpisode.files, camera) : null
                const expanded = expandedCamera === camera
                const collapsed = expandedCamera && expandedCamera !== camera
                return (
                  <div
                    key={camera}
                    className={`coupon-video-cell${expanded ? ' is-expanded' : ''}${collapsed ? ' is-collapsed' : ''}`}
                    onClick={() => setExpandedCamera((current) => current === camera ? null : camera)}
                  >
                    {videoUrl ? (
                      <video
                        ref={(node) => { videoRefs.current[camera] = node }}
                        src={videoUrl}
                        muted
                        playsInline
                        preload="metadata"
                        onTimeUpdate={camera === cameras[0] ? handleLeaderTimeUpdate : undefined}
                        onPlay={camera === cameras[0] ? handlePlayStateChange : undefined}
                        onPause={camera === cameras[0] ? handlePlayStateChange : undefined}
                        onEnded={camera === cameras[0] ? handlePlayStateChange : undefined}
                      />
                    ) : (
                      <div className="coupon-video-empty">Missing video</div>
                    )}
                    <span className="coupon-camera-label">{camera}</span>
                  </div>
                )
              })}
              {!cameras.length ? <div className="coupon-video-empty">No cameras available</div> : null}
            </div>

            <div className="coupon-plot-column">
              {loadingEpisode ? (
                <div className="coupon-plot-card"><div className="coupon-plot-empty">Loading episode…</div></div>
              ) : parsedData?.series.length ? (
                parsedData.series.map((series) => (
                  <TimeSeriesPlot
                    key={series.key}
                    series={series}
                    frameIndices={parsedData.frameIndices}
                    currentFrame={currentFrame}
                    syncKey={`manifest-${manifestId}`}
                  />
                ))
              ) : (
                <div className="coupon-plot-card"><div className="coupon-plot-empty">No parsed numeric series</div></div>
              )}
            </div>
          </div>

          <div className="coupon-controls">
            <div className="coupon-controls-buttons">
              <Button
                type="button"
                variant="ghost"
                onClick={() => stepFrame(-1)}
                disabled={!selectedEpisode}
                title="Previous frame"
              >
                ‹
              </Button>
              <Button
                type="button"
                variant="primary"
                onClick={togglePlay}
                disabled={!selectedEpisode}
              >
                {isPlaying ? 'Pause' : 'Play'}
              </Button>
              <Button
                type="button"
                variant="ghost"
                onClick={() => stepFrame(1)}
                disabled={!selectedEpisode}
                title="Next frame"
              >
                ›
              </Button>
            </div>
            <input
              className="coupon-scrubber"
              type="range"
              min="0"
              max="1000"
              value={selectedEpisode && maxFrameIndex > 0 ? Math.round((currentFrame / maxFrameIndex) * 1000) : 0}
              onChange={(event) => scrubToFraction(Number(event.target.value) / 1000)}
              disabled={!selectedEpisode}
            />
            <div className="coupon-controls-time">
              {manifest.fps && maxFrameIndex > 0
                ? `${formatPlaybackTime(currentFrame / manifest.fps)} / ${formatPlaybackTime(maxFrameIndex / manifest.fps)}`
                : `${currentFrame} / ${maxFrameIndex}`}
            </div>
          </div>
        </main>

        <aside className="coupon-metrics coupon-metadata">
          <section className="coupon-metadata-section">
            <div className="coupon-metadata-title">
              <h3>Dataset</h3>
              <span className={`coupon-type-tag coupon-type-${manifest.type}`}>{manifest.type}</span>
            </div>
            <div className="coupon-metadata-name">{manifest.name}</div>
            <div className="coupon-meta-row">
              <span>UUID</span>
              <span className="coupon-meta-uuid">
                <span className="coupon-meta-mono" title={manifest.id}>{manifest.id}</span>
                <CopyIdButton value={manifest.id} />
              </span>
            </div>
            <div
              className={`coupon-metadata-success${manifest.success_rate === null ? ' is-empty' : ''}`}
            >
              <span className="coupon-success-value">
                {manifest.success_rate !== null
                  ? `${Math.round(manifest.success_rate * 100)}%`
                  : '—%'}
              </span>
              <span className="coupon-success-sublabel">
                success · {manifest.rated_episodes}/{manifest.episode_count} rated
              </span>
            </div>
            <LinkedRunsCarousel
              runs={linkedRuns}
              activeIndex={activeLinkedRunIndex}
              onPrevious={goPreviousLinkedRun}
              onNext={goNextLinkedRun}
            />
            {linkedRunsError && manifest.run_ids.length > 0 ? (
              <div className="coupon-linked-run-error">
                <strong>Linked runs unavailable locally</strong>
                <span>{manifest.run_ids.join(', ')}</span>
              </div>
            ) : null}
            {manifest.description ? (
              <p className="coupon-metadata-desc">{manifest.description}</p>
            ) : null}
            {manifest.tags.length > 0 ? (
              <div className="coupon-metadata-tags">
                {manifest.tags.map((tag) => (
                  <span key={tag} className="coupon-metadata-tag">{tag}</span>
                ))}
              </div>
            ) : null}
          </section>

          <section className="coupon-metadata-section">
            <h3>Dataset Info</h3>
            <div className="coupon-meta-row"><span>FPS</span><span>{manifest.fps ?? '—'}</span></div>
            <div className="coupon-meta-row"><span>Episodes</span><span>{manifest.episode_count}</span></div>
            <div className="coupon-meta-row"><span>Cameras</span><span>{cameras.length}</span></div>
            <div className="coupon-meta-row"><span>Features</span><span>{Object.keys(manifest.features).length}</span></div>
          </section>

          {selectedEpisode ? (
            <section className="coupon-metadata-section">
              <h3>Episode</h3>
              <div className="coupon-meta-row">
                <span>UUID</span>
                <span className="coupon-meta-uuid">
                  <span className="coupon-meta-mono" title={selectedEpisode.id}>{selectedEpisode.id}</span>
                  <CopyIdButton value={selectedEpisode.id} />
                </span>
              </div>
              <div className="coupon-meta-row">
                <span>Recorded</span>
                <span>{formatEpisodeTimestamp(selectedEpisode.created_at)}</span>
              </div>
              <div className="coupon-meta-row"><span>Frames</span><span>{selectedEpisode.length}</span></div>
              {selectedEpisode.collection_mode ? (
                <div className="coupon-meta-row"><span>Mode</span><span>{selectedEpisode.collection_mode}</span></div>
              ) : null}
              {selectedEpisode.task ? (
                <div className="coupon-meta-row"><span>Task</span><span>{selectedEpisode.task}</span></div>
              ) : null}
              <div className="coupon-meta-row">
                <span>Reward</span>
                <span
                  className={`coupon-reward-pill${
                    selectedEpisode.reward === 1
                      ? ' is-success'
                      : selectedEpisode.reward === 0
                      ? ' is-fail'
                      : ''
                  }`}
                >
                  {selectedEpisode.reward === null ? 'unrated' : selectedEpisode.reward.toFixed(2)}
                </span>
              </div>
              {selectedEpisode.task_description ? (
                <p className="coupon-metadata-desc">{selectedEpisode.task_description}</p>
              ) : null}
            </section>
          ) : null}

          {selectedEpisode
            && (selectedEpisode.source_run_id
              || selectedEpisode.policy_name
              || selectedEpisode.source_checkpoint) ? (
            <section className="coupon-metadata-section">
              <h3>Provenance</h3>
              {selectedEpisode.policy_name ? (
                <div className="coupon-meta-row"><span>Policy</span><span>{selectedEpisode.policy_name}</span></div>
              ) : null}
              {selectedEpisode.source_checkpoint ? (
                <div className="coupon-meta-row">
                  <span>Checkpoint</span>
                  <span className="coupon-meta-mono">{selectedEpisode.source_checkpoint}</span>
                </div>
              ) : null}
              {selectedEpisode.source_run_id ? (
                <div className="coupon-meta-row">
                  <span>Run</span>
                  {selectedEpisode.source_project_id ? (
                    <Link
                      data-tour="run-link"
                      to={`/projects/${selectedEpisode.source_project_id}/runs/${selectedEpisode.source_run_id}`}
                      className="coupon-meta-link coupon-meta-mono"
                      title={selectedEpisode.source_run_id}
                    >
                      {selectedEpisode.source_run_id.slice(0, 8)}
                    </Link>
                  ) : (
                    <span className="coupon-meta-mono" title={selectedEpisode.source_run_id}>
                      {selectedEpisode.source_run_id.slice(0, 8)}
                    </span>
                  )}
                </div>
              ) : null}
            </section>
          ) : null}

          {Object.keys(manifest.features).length > 0 ? (
            <section className="coupon-metadata-section">
              <h3>Features</h3>
              {Object.entries(manifest.features).map(([key, spec]) => (
                <div key={key} className="coupon-meta-row coupon-meta-row-feature">
                  <span className="coupon-meta-mono" title={key}>{key}</span>
                  <span className="coupon-meta-mono">
                    {spec.dtype === 'video' ? 'video' : `[${spec.shape?.join(',') ?? '?'}]`}
                  </span>
                </div>
              ))}
            </section>
          ) : null}
        </aside>
      </div>

      {toasts.length > 0 ? (
        <div className="coupon-toast-host">
          {toasts.map((toast) => (
            <div
              key={toast.id}
              className={`coupon-toast${toast.tone === 'error' ? ' coupon-toast-error' : ''}`}
            >
              {toast.message}
            </div>
          ))}
        </div>
      ) : null}
    </div>
  )
}
