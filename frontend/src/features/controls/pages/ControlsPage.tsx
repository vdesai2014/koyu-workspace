// Controls tab — placeholder.
//
// The live robot-control surface (joint telemetry, camera feeds, enable/estop)
// is rewired here as the runtime services come online over the bridge. Until
// those services exist it stays an empty state and talks to no backend, so this
// page imports neither the bridge hooks nor the recording-context api.

export function ControlsPage() {
  return (
    <section className="home-welcome">
      <p className="eyebrow">Controls</p>
      <h1>No runtime connected.</h1>
      <p>Live robot telemetry and controls appear here once the runtime services are online.</p>
    </section>
  )
}
