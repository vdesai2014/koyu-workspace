import { useEffect, useRef } from 'react'
import uPlot from 'uplot'
import 'uplot/dist/uPlot.min.css'

import type { ParsedSeries } from './types'

// Series palette tuned against the copper UI
const SERIES_COLORS = [
  '#f6c17f', '#7ec8e3', '#db8dd0', '#86cf9c', '#f08d49', '#d9db85', '#c9a0dc',
]

interface TimeSeriesPlotProps {
  series: ParsedSeries
  frameIndices: number[]
  currentFrame?: number
  syncKey?: string
}

export function TimeSeriesPlot({ series, frameIndices, currentFrame, syncKey }: TimeSeriesPlotProps) {
  const containerRef = useRef<HTMLDivElement>(null)
  const plotRef = useRef<uPlot | null>(null)
  // Draw hook closes over this ref so currentFrame changes don't require re-init
  const currentFrameRef = useRef<number | undefined>(currentFrame)
  currentFrameRef.current = currentFrame

  useEffect(() => {
    if (!containerRef.current) return
    if (!frameIndices.length || !series.rows.length) return

    const numDims = series.rows[0]?.length ?? 0
    if (numDims === 0) return

    // uPlot wants aligned column-major data: [x[], y1[], y2[], ...]
    const yColumns: number[][] = []
    for (let dim = 0; dim < numDims; dim += 1) {
      yColumns.push(series.rows.map((row) => row[dim]))
    }
    const data: uPlot.AlignedData = [frameIndices, ...yColumns]

    const uSeries: uPlot.Series[] = [{}]
    for (let dim = 0; dim < numDims; dim += 1) {
      uSeries.push({
        label: series.names[dim] ?? `dim ${dim}`,
        stroke: SERIES_COLORS[dim % SERIES_COLORS.length],
        width: 1.5,
      })
    }

    const axisCommon = {
      stroke: 'rgba(230, 230, 220, 0.45)',
      grid: { stroke: 'rgba(255, 255, 255, 0.06)' },
      ticks: { stroke: 'rgba(255, 255, 255, 0.18)' },
      font: '10px "Space Mono", ui-monospace, monospace',
    }

    const opts: uPlot.Options = {
      width: containerRef.current.clientWidth,
      height: Math.max(120, containerRef.current.clientHeight),
      series: uSeries,
      scales: { x: { time: false } },
      axes: [axisCommon, { ...axisCommon, size: 36 }],
      legend: { show: false },
      cursor: {
        show: true,
        drag: { x: true, y: false },
        ...(syncKey ? { sync: { key: syncKey } } : {}),
      },
      hooks: {
        draw: [
          (u) => {
            const frame = currentFrameRef.current
            if (frame === undefined) return
            const x = u.valToPos(frame, 'x', true)
            if (!Number.isFinite(x)) return
            const { ctx } = u
            const top = u.bbox.top
            const bottom = u.bbox.top + u.bbox.height
            ctx.save()
            ctx.strokeStyle = 'rgba(196, 121, 63, 0.7)'
            ctx.lineWidth = 1.5
            ctx.setLineDash([4, 3])
            ctx.beginPath()
            ctx.moveTo(x, top)
            ctx.lineTo(x, bottom)
            ctx.stroke()
            ctx.restore()
          },
        ],
      },
    }

    const plot = new uPlot(opts, data, containerRef.current)
    plotRef.current = plot

    const handleResize = () => {
      if (!containerRef.current) return
      plot.setSize({
        width: containerRef.current.clientWidth,
        height: Math.max(120, containerRef.current.clientHeight),
      })
    }
    const observer = new ResizeObserver(handleResize)
    observer.observe(containerRef.current)

    return () => {
      observer.disconnect()
      plot.destroy()
      plotRef.current = null
    }
  }, [series, frameIndices, syncKey])

  // Re-run the draw hook (which paints the current-frame indicator) when the
  // playhead moves. Cheap — no path rebuild, no axis recompute.
  useEffect(() => {
    if (plotRef.current) {
      plotRef.current.redraw(false, false)
    }
  }, [currentFrame])

  return (
    <div className="coupon-plot-card">
      <div className="coupon-plot-header">
        <span className="coupon-plot-title">{series.key}</span>
        <div className="coupon-plot-legend">
          {series.names.length > 0
            ? series.names.map((name, idx) => (
                <span key={`${series.key}-${name}-${idx}`} style={{ color: SERIES_COLORS[idx % SERIES_COLORS.length] }}>
                  {name}
                </span>
              ))
            : Array.from({ length: series.rows[0]?.length ?? 0 }, (_, idx) => (
                <span key={`${series.key}-dim${idx}`} style={{ color: SERIES_COLORS[idx % SERIES_COLORS.length] }}>
                  dim {idx}
                </span>
              ))}
        </div>
      </div>
      <div className="coupon-plot-canvas" ref={containerRef} />
    </div>
  )
}
