import * as arrow from 'apache-arrow'
import initParquet, { readParquet } from 'parquet-wasm'
import parquetWasmUrl from 'parquet-wasm/esm/parquet_wasm_bg.wasm?url'

import type { DatasetEpisodeDetail, ParsedEpisodeData, ParsedSeries } from './types'

let wasmInitPromise: Promise<unknown> | null = null

async function ensureParquetInit() {
  if (!wasmInitPromise) {
    wasmInitPromise = initParquet(parquetWasmUrl)
  }
  await wasmInitPromise
}

function toNumberArray(value: unknown): number[] {
  if (value == null) return []
  const iterable = typeof (value as { toArray?: () => unknown }).toArray === 'function'
    ? Array.from((value as { toArray: () => Iterable<unknown> }).toArray())
    : Array.isArray(value)
      ? value
      : Array.from(value as Iterable<unknown>)
  return iterable.map((item) => (typeof item === 'bigint' ? Number(item) : Number(item)))
}

function getSeriesKeys(detail: DatasetEpisodeDetail): string[] {
  return Object.entries(detail.features)
    .filter(([, spec]) => spec.dtype && spec.dtype !== 'video')
    .map(([key]) => key)
}

export async function parseEpisodeParquet(
  parquetUrl: string,
  detail: DatasetEpisodeDetail,
): Promise<ParsedEpisodeData> {
  await ensureParquetInit()
  const response = await fetch(parquetUrl, { cache: 'no-store' })
  if (!response.ok) {
    throw new Error(`Parquet fetch failed with ${response.status}`)
  }

  const bytes = new Uint8Array(await response.arrayBuffer())
  const wasmTable = readParquet(bytes)
  const ipcStream = wasmTable.intoIPCStream()
  const table = arrow.tableFromIPC(ipcStream)

  const frameIndexColumn = table.getChild('frame_index')
  const timestampColumn = table.getChild('timestamp')
  const frameIndices: number[] = []
  const timestamps: number[] = []

  for (let row = 0; row < table.numRows; row += 1) {
    const frameIndex = frameIndexColumn?.get(row)
    const timestamp = timestampColumn?.get(row)
    frameIndices.push(typeof frameIndex === 'bigint' ? Number(frameIndex) : Number(frameIndex ?? row))
    timestamps.push(typeof timestamp === 'bigint' ? Number(timestamp) : Number(timestamp ?? row))
  }

  const series: ParsedSeries[] = []
  for (const key of getSeriesKeys(detail)) {
    const column = table.getChild(key)
    if (!column) continue
    const names = detail.features[key]?.names ?? []
    const rows: number[][] = []
    for (let row = 0; row < table.numRows; row += 1) {
      rows.push(toNumberArray(column.get(row)))
    }
    series.push({ key, names, rows })
  }

  return { frameIndices, timestamps, series }
}
