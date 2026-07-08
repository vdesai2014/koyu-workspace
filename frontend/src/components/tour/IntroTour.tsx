import React, { Suspense, useCallback, useEffect, useRef, useState } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import type { EventData } from 'react-joyride'

const Joyride = React.lazy(() =>
  import('react-joyride').then((m) => ({ default: m.Joyride })),
)

// Tours are gated purely on the URL param (`?tour=intro` or
// `?tour=intro2`). Visiting plain `/` is the no-tour state; the
// query-bearing URL always replays. No localStorage involved —
// re-running is just a refresh.

const IL_MANIFEST_NAME = 'eval-imitation-learning-grasp-pickup'
const ACT_PPO_MANIFEST_NAME = 'eval-act-ppo-grasp-pickup'

type Auto =
  | { kind: 'run-il-eval'; runMs: number; settleMs: number }
  | { kind: 'run-act-ppo-eval'; maxWaitMs: number; settleMs: number }
  | { kind: 'enter-manifest'; manifestName: string }
  | { kind: 'enter-run-from-link' }

type Route =
  | string
  | { kind: 'manifest-detail'; manifestName: string }
  | { kind: 'run-from-link' }

interface TourStep {
  target: string
  title?: string
  content: string
  route: Route
  auto?: Auto
  placement?: 'top' | 'bottom' | 'left' | 'right' | 'auto'
  skipBeacon?: boolean
  overlayClickAction?: 'close' | 'next' | false
  blockTargetInteraction?: boolean
}

const STEPS_INTRO_1: TourStep[] = [
  {
    target: '[data-tour="manifest-name"]',
    route: '/controls',
    title: 'Eval manifest, set by the agent',
    content:
      "This is the eval manifest the agent created via NATS during prep — name, type, source run, source checkpoint were all set without you typing anything. The agent can update this from the terminal as you iterate, so new policies get tracked under the right manifest automatically.",
    skipBeacon: true,
    placement: 'left',
  },
  {
    target: '[data-tour="start-eval"]',
    route: '/controls',
    title: 'Run the IL eval',
    content:
      "This is Start Eval. Click Next and the tour will run a short eval on the imitation-learning policy for you — it'll struggle, that's the point.",
    placement: 'top',
    skipBeacon: true,
  },
  {
    target: '[data-tour="start-eval"]',
    route: '/controls',
    title: 'Watching the IL policy fail…',
    content:
      "Running for ~5 seconds, then auto-cancelling. You'll see the robot reach, hesitate, and never quite close the gripper.",
    auto: { kind: 'run-il-eval', runMs: 5000, settleMs: 1500 },
    placement: 'top',
    skipBeacon: true,
  },
  {
    target: `[data-tour-manifest="${IL_MANIFEST_NAME}"]`,
    route: '/datasets',
    title: 'Your eval landed here',
    content:
      "The recorder wrote the eval as a new episode under this manifest, with full lineage to the IL run. Click Next to open it.",
    placement: 'right',
    skipBeacon: true,
  },
  {
    target: '[data-tour="thumbs"]',
    route: { kind: 'manifest-detail', manifestName: IL_MANIFEST_NAME },
    title: 'Label the result',
    content:
      "Thumbs up = success, thumbs down = fail. Click either; the rating travels with the episode if you push to koyu.dev later. Hit Next when you're ready to keep going.",
    placement: 'right',
    skipBeacon: true,
    overlayClickAction: false,
    blockTargetInteraction: false,
  },
  {
    target: '[data-tour="run-link"]',
    route: { kind: 'manifest-detail', manifestName: IL_MANIFEST_NAME },
    title: 'The source run',
    content:
      "This link points at the imitation-learning training run that produced the checkpoint behind this eval. Click Next to navigate there.",
    placement: 'left',
    skipBeacon: true,
    overlayClickAction: false,
    blockTargetInteraction: false,
  },
  {
    target: '[data-tour="run-outputs"]',
    route: { kind: 'run-from-link' },
    title: 'Where the eval will be linked',
    content:
      "This is the IL run page. The Manifests section is empty right now — but when you return to the agent and continue, the agent will associate the eval manifest you just generated with this run. That's the bond between an eval and the code/checkpoint that produced it: a single bidirectional link, agent-managed, automatic.",
    placement: 'top',
    skipBeacon: true,
  },
]

const STEPS_INTRO_2: TourStep[] = [
  {
    target: '[data-tour="start-eval"]',
    route: '/controls',
    title: 'Run the ACT+PPO eval',
    content:
      "Click Next and the tour will run the ACT+PPO eval — it usually succeeds in a few seconds (the policy is ~98%). Tour will wait up to ~20s for the eval to finish, then move to the new episode.",
    auto: { kind: 'run-act-ppo-eval', maxWaitMs: 22000, settleMs: 1500 },
    placement: 'top',
    skipBeacon: true,
  },
  {
    target: `[data-tour-manifest="${ACT_PPO_MANIFEST_NAME}"]`,
    route: '/datasets',
    title: 'New episode, with lineage',
    content:
      "The ACT+PPO eval landed as a new episode under its own manifest, with lineage to the ACT+PPO training run. You now have two evals side by side — same task, different architecture. (ACT+PPO is ~98% success — if this run happened to fail, refresh the URL to re-roll.)",
    placement: 'right',
    skipBeacon: true,
  },
]

function waitForSelector(selector: string, timeoutMs = 5000): Promise<HTMLElement | null> {
  return new Promise((resolve) => {
    const existing = document.querySelector(selector) as HTMLElement | null
    if (existing) {
      resolve(existing)
      return
    }
    const start = Date.now()
    const interval = window.setInterval(() => {
      const found = document.querySelector(selector) as HTMLElement | null
      if (found) {
        window.clearInterval(interval)
        resolve(found)
        return
      }
      if (Date.now() - start > timeoutMs) {
        window.clearInterval(interval)
        resolve(null)
      }
    }, 200)
  })
}

/**
 * Poll the eval-state DOM label until it shows a terminal state
 * (SUCCESS / TIMEOUT / CANCELLED), or until timeoutMs elapses.
 */
function waitForEvalTerminal(timeoutMs: number): Promise<string | null> {
  return new Promise((resolve) => {
    const start = Date.now()
    const interval = window.setInterval(() => {
      const el = document.querySelector('[data-tour="eval-state"]') as HTMLElement | null
      const text = (el?.textContent || '').trim().toUpperCase()
      if (text === 'SUCCESS' || text === 'TIMEOUT' || text === 'CANCELLED') {
        window.clearInterval(interval)
        resolve(text)
        return
      }
      if (Date.now() - start > timeoutMs) {
        window.clearInterval(interval)
        resolve(null)
      }
    }, 200)
  })
}

async function fetchManifestId(name: string): Promise<string | null> {
  try {
    const res = await fetch('/api/manifests?type=eval')
    const data = await res.json()
    const manifests = (data?.manifests ?? []) as Array<{ id: string; name: string }>
    const match = manifests.find((m) => m.name === name)
    return match?.id ?? null
  } catch {
    return null
  }
}

/**
 * Resolve a step's route to a concrete pathname. Returns null if
 * we cannot resolve (e.g., manifest doesn't exist yet, or
 * run-from-link can't find the link element).
 */
async function resolveRoute(route: Route): Promise<string | null> {
  if (typeof route === 'string') return route
  if (route.kind === 'manifest-detail') {
    const manifestId = await fetchManifestId(route.manifestName)
    return manifestId ? `/datasets/${manifestId}` : null
  }
  if (route.kind === 'run-from-link') {
    const linkEl = document.querySelector('[data-tour="run-link"]') as HTMLAnchorElement | null
    if (!linkEl) return null
    // Prefer the React-Router-resolved pathname; fall back to href.
    const path = linkEl.pathname || linkEl.getAttribute('href') || ''
    return path || null
  }
  return null
}

export function IntroTour() {
  const location = useLocation()
  const navigate = useNavigate()
  const [run, setRun] = useState(false)
  const [stepIndex, setStepIndex] = useState(0)
  const [tourReady, setTourReady] = useState(false)
  const [tourKind, setTourKind] = useState<'intro' | 'intro2' | null>(null)
  const [bootstrapped, setBootstrapped] = useState(false)
  const inFlight = useRef(false)

  const STEPS = tourKind === 'intro2' ? STEPS_INTRO_2 : STEPS_INTRO_1

  // Decide which tour to run on this mount and bootstrap it.
  useEffect(() => {
    if (typeof window === 'undefined') return
    if (bootstrapped) return
    const params = new URLSearchParams(window.location.search)
    const requestedKind =
      params.get('tour') === 'intro2'
        ? 'intro2'
        : params.get('tour') === 'intro'
        ? 'intro'
        : null
    if (!requestedKind) return

    setBootstrapped(true)
    setTourKind(requestedKind)

    const STEPS_LOCAL = requestedKind === 'intro2' ? STEPS_INTRO_2 : STEPS_INTRO_1
    void (async () => {
      const path = await resolveRoute(STEPS_LOCAL[0].route)
      if (path && location.pathname !== path) {
        navigate(path, { replace: false })
      }
      const target = await waitForSelector(STEPS_LOCAL[0].target, 6000)
      if (target) {
        setRun(true)
        setStepIndex(0)
        setTourReady(true)
      }
    })()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bootstrapped])

  // Run side-effects when entering an auto-step.
  useEffect(() => {
    if (!run || !tourReady) return
    const step = STEPS[stepIndex]
    if (!step?.auto) return
    if (inFlight.current) return
    inFlight.current = true

    let cancelled = false
    const cleanups: Array<() => void> = []

    const advanceNext = async () => {
      const next = stepIndex + 1
      if (next >= STEPS.length) {
        setRun(false)
        return
      }
      const nextStep = STEPS[next]
      const path = await resolveRoute(nextStep.route)
      if (path && path !== location.pathname) {
        navigate(path)
      }
      const target = await waitForSelector(nextStep.target, 6000)
      if (cancelled) return
      if (target) {
        setStepIndex(next)
      } else {
        // eslint-disable-next-line no-console
        console.warn('[IntroTour] target not found for step', next, nextStep.target)
        setRun(false)
      }
      inFlight.current = false
    }

    if (step.auto.kind === 'run-il-eval') {
      const { runMs, settleMs } = step.auto
      const startBtn = document.querySelector('[data-tour="start-eval"]') as HTMLElement | null
      if (startBtn) startBtn.click()
      const cancelTimer = window.setTimeout(() => {
        const cancelBtn = document.querySelector('[data-tour="start-eval"]') as HTMLElement | null
        if (cancelBtn) cancelBtn.click()
        const settleTimer = window.setTimeout(() => {
          if (!cancelled) void advanceNext()
        }, settleMs)
        cleanups.push(() => window.clearTimeout(settleTimer))
      }, runMs)
      cleanups.push(() => window.clearTimeout(cancelTimer))
    } else if (step.auto.kind === 'run-act-ppo-eval') {
      const { maxWaitMs, settleMs } = step.auto
      const startBtn = document.querySelector('[data-tour="start-eval"]') as HTMLElement | null
      if (startBtn) startBtn.click()
      void (async () => {
        await waitForEvalTerminal(maxWaitMs)
        if (cancelled) return
        const settleTimer = window.setTimeout(() => {
          if (!cancelled) void advanceNext()
        }, settleMs)
        cleanups.push(() => window.clearTimeout(settleTimer))
      })()
    } else {
      // No-op for other auto kinds — manual handler advances.
      inFlight.current = false
    }

    return () => {
      cancelled = true
      for (const cleanup of cleanups) cleanup()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [run, tourReady, stepIndex])

  // Manual advance/back handler for Joyride's Next/Back/Close events.
  const handleEvent = useCallback(
    async (data: EventData) => {
      const { action, lifecycle, status } = data as unknown as {
        action?: string
        lifecycle?: string
        status?: string
      }
      if (
        status === 'finished' ||
        status === 'skipped' ||
        action === 'close' ||
        action === 'skip'
      ) {
        setRun(false)
        setStepIndex(0)
        inFlight.current = false
        return
      }
      if (lifecycle !== 'complete') return
      const step = STEPS[stepIndex]
      if (!step) return
      // Auto steps drive their own advancement via the effect above.
      if (step.auto?.kind === 'run-il-eval' || step.auto?.kind === 'run-act-ppo-eval') return

      if (action === 'next') {
        const next = stepIndex + 1
        if (next >= STEPS.length) {
          setRun(false)
          return
        }
        const nextStep = STEPS[next]
        const path = await resolveRoute(nextStep.route)
        if (path && path !== location.pathname) {
          navigate(path)
        }
        const target = await waitForSelector(nextStep.target, 6000)
        if (target) {
          setStepIndex(next)
        } else {
          // eslint-disable-next-line no-console
          console.warn('[IntroTour] target not found for step', next, nextStep.target)
          setRun(false)
        }
      } else if (action === 'prev') {
        const prev = Math.max(0, stepIndex - 1)
        setStepIndex(prev)
      }
    },
    [STEPS, location.pathname, navigate, stepIndex, tourKind],
  )

  if (!run) return null

  return (
    <Suspense fallback={null}>
      <Joyride
        steps={STEPS as unknown as never}
        run={run}
        stepIndex={stepIndex}
        continuous
        onEvent={handleEvent}
      />
    </Suspense>
  )
}
