// Controls: your robot's control surface. This page ships empty on purpose,
// since every robot's controls are different, and building it belongs to
// your agent. The primer for wiring runtime data into any browser surface
// (the four data primitives and the liveness rules) lives at the top of
// src/lib/useBridge.ts, which is also the reference client. The controls-*
// classes in index.css (cards, badges, camera tiles, signal rows) are
// ready-made if you want the house look.
//
// One hard-won rule for video, worth stating twice (the primer has the
// details): point MJPEG <img> tags at the bridge origin directly
// (http://<host>:8765/mjpeg/<topic>), never through the vite /bridge proxy.
// Browsers park aborted multipart streams in the app origin's 6-connection
// pool, so a few visits to a proxied-camera page stall every fetch and even
// page refreshes across the whole app. Give video its own origin, and clear
// each img.src when this page unmounts so the streams end with it.

export function ControlsPage() {
  return (
    <section className="home-welcome">
      <p className="eyebrow">Controls</p>
      <h1>No controls built yet.</h1>
      <p>
        Every robot's control surface is different, so this page ships empty.
        Point your coding agent at this file: its comments say where the
        wiring primer lives.
      </p>
    </section>
  )
}
