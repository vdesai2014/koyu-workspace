// Controls — your robot's control surface. Deliberately empty in the stock
// workspace: every robot's controls are different, so this page belongs to
// your agent. The plumbing below is universal; the widgets are not, and no
// framework here will pretend otherwise.
//
// ── The four data primitives ──────────────────────────────────────────────
// Every robot UI reduces to four kinds of data movement, each one bridge
// verb away (helpers in src/lib/useBridge.ts; the bridge resolves struct
// types from the runtime's services.yaml, so no schemas live client-side —
// a topic must be declared in a service's ipc block for the bridge to know it):
//
// 1. LIVE TELEMETRY (numbers, text, badges)
//      const t = useTopic<YourCell>('arm/state', 'ArmState', 10)
//      Latest cell as JSON at ~10 Hz, deduped by frame_id. Works for
//      blackboard cells and pub/sub streams alike.
//
// 2. TIME SERIES (plots, deltas, histories)
//      Same subscription; the bridge is latest-value by design, so history
//      is yours to keep: accumulate samples into a ring buffer as they
//      arrive. features/datasets/TimeSeriesPlot.tsx is a ready renderer.
//
// 3. VIDEO (camera feeds)
//      <img src={`/bridge/mjpeg/${topic}`} />
//      Multipart push stream, one connection per viewer, cap with ?fps=.
//      /bridge/frame/<topic> returns a single JPEG snapshot. Feeds stream
//      while the publisher publishes; late joiners get the cached last frame.
//
// 4. VERBS (buttons, estop, mode switches)
//      ringEvent('arm/control', EVENT_ID)   fire a payload-less doorbell
//      useEventFeed('arm/events')           hear ring-backs
//      set-param (see useBridge) for tunable values via the param server.
//
// ── Liveness rules (paid for in scar tissue) ──────────────────────────────
// - Connection state is not data state: the page can be connected while
//   nothing publishes. Design an empty state for every widget.
// - There is no history for late joiners: a fresh subscription sees the
//   NEXT sample, not the last one (cameras excepted, via the bridge cache).
// - Publishers pause; feeds pause with them. Widgets must idle gracefully.
//
// The controls-* classes in index.css (cards, badges, camera tiles, signal
// rows) are ready-made if you want the house look.

export function ControlsPage() {
  return (
    <section className="home-welcome">
      <p className="eyebrow">Controls</p>
      <h1>No controls built yet.</h1>
      <p>
        Every robot's control surface is different, so this page ships empty.
        Point your coding agent at this file: the comments explain the four
        data primitives and the bridge plumbing it needs to build yours.
      </p>
    </section>
  )
}
