// The bridge client: how ANY browser surface reaches the runtime. This file
// is the reference implementation for the four data primitives, and the
// primer below applies to whatever you are building, a controls page, a 3D
// visualizer, a teleop panel.
//
// ── The four data primitives ──────────────────────────────────────────────
// Every robot UI reduces to four kinds of data movement, each one bridge
// verb away. The bridge resolves struct types from the runtime's
// services.yaml, so no schemas live client-side. A topic must be declared
// in a service's ipc block for the bridge to know it.
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
//      set-param (below) for tunable values via the param server.
//
// ── Liveness rules (paid for in scar tissue) ──────────────────────────────
// - Connection state is not data state: the page can be connected while
//   nothing publishes. Design an empty state for every widget.
// - There is no history for late joiners: a fresh subscription sees the
//   NEXT sample, not the last one (cameras excepted, via the bridge cache).
// - Publishers pause; feeds pause with them. Widgets must idle gracefully.

import { useEffect, useRef, useState, useCallback } from 'react'

const WS_URL = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws`
const RECONNECT_MS = 2000

type TopicData = {
  timestamp: number
  frame_id: number
  values: Record<string, unknown>
}

type NatsCallback = (payload: unknown) => void

type PendingRequest = {
  resolve: (value: unknown) => void
  reject: (reason?: unknown) => void
}

let ws: WebSocket | null = null
let wsReady = false
const listeners = new Map<string, Set<(d: TopicData) => void>>()
const activeSubs = new Map<string, { type_name: string; rate_hz: number; refcount: number }>()
const natsListeners = new Map<string, Set<NatsCallback>>()
const eventListeners = new Map<string, Set<(event_id: number) => void>>()
const pendingRequests = new Map<string, PendingRequest>()
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
const pendingMessages: Record<string, unknown>[] = []
let nextReqId = 1

function ensureConnection() {
  if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) return
  connect()
}

function connect() {
  ws = new WebSocket(WS_URL)

  ws.onopen = () => {
    wsReady = true
    for (const [topic, info] of activeSubs) {
      ws!.send(JSON.stringify({ type: 'subscribe-topic', topic, type_name: info.type_name, rate_hz: info.rate_hz }))
    }
    for (const subject of natsListeners.keys()) {
      ws!.send(JSON.stringify({ type: 'nats-subscribe', subject }))
    }
    for (const channel of eventListeners.keys()) {
      ws!.send(JSON.stringify({ type: 'listen-event', channel }))
    }
    while (pendingMessages.length > 0) {
      ws!.send(JSON.stringify(pendingMessages.shift()!))
    }
  }

  ws.onmessage = (ev) => {
    try {
      const msg = JSON.parse(ev.data)
      if (msg.type === 'topic-data') {
        const cbs = listeners.get(msg.topic)
        if (cbs) cbs.forEach((cb) => cb(msg))
      } else if (msg.type === 'event') {
        const cbs = eventListeners.get(msg.channel)
        if (cbs) cbs.forEach((cb) => cb(msg.event_id))
      } else if (msg.type === 'nats-message') {
        const cbs = natsListeners.get(msg.subject)
        if (cbs) cbs.forEach((cb) => cb(msg.payload))
      } else if (msg.type === 'nats-response') {
        const pending = pendingRequests.get(msg.req_id)
        if (!pending) return
        pendingRequests.delete(msg.req_id)
        if (msg.error) pending.reject(new Error(msg.error))
        else pending.resolve(msg.payload)
      }
    } catch {
      // ignore parse errors
    }
  }

  ws.onclose = () => {
    wsReady = false
    if (!reconnectTimer) {
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        connect()
      }, RECONNECT_MS)
    }
  }

  ws.onerror = () => ws?.close()
}

function send(msg: Record<string, unknown>) {
  if (ws && wsReady) {
    ws.send(JSON.stringify(msg))
    return
  }
  pendingMessages.push(msg)
}

function subscribe(topic: string, type_name: string, rate_hz: number, cb: (d: TopicData) => void) {
  if (!listeners.has(topic)) listeners.set(topic, new Set())
  listeners.get(topic)!.add(cb)

  const existing = activeSubs.get(topic)
  if (existing) {
    existing.refcount++
  } else {
    activeSubs.set(topic, { type_name, rate_hz, refcount: 1 })
    ensureConnection()
    send({ type: 'subscribe-topic', topic, type_name, rate_hz })
  }

  return () => {
    listeners.get(topic)?.delete(cb)
    const info = activeSubs.get(topic)
    if (info) {
      info.refcount--
      if (info.refcount <= 0) {
        activeSubs.delete(topic)
        send({ type: 'unsubscribe-topic', topic })
      }
    }
  }
}

function subscribeNats(subject: string, cb: NatsCallback) {
  if (!natsListeners.has(subject)) natsListeners.set(subject, new Set())
  const listenersForSubject = natsListeners.get(subject)!
  const shouldSubscribe = listenersForSubject.size === 0
  listenersForSubject.add(cb)
  ensureConnection()
  if (shouldSubscribe) send({ type: 'nats-subscribe', subject })

  return () => {
    const next = natsListeners.get(subject)
    if (!next) return
    next.delete(cb)
    if (next.size === 0) {
      natsListeners.delete(subject)
      send({ type: 'nats-unsubscribe', subject })
    }
  }
}

export async function natsRequest<T = unknown>(subject: string, payload: unknown = {}): Promise<T> {
  ensureConnection()
  const reqId = `req-${nextReqId++}`
  const promise = new Promise<T>((resolve, reject) => {
    pendingRequests.set(reqId, { resolve: resolve as (value: unknown) => void, reject })
  })
  send({ type: 'nats-request', req_id: reqId, subject, payload })
  return promise
}

export function useTopic<T = Record<string, unknown>>(topic: string, type_name: string, rate_hz = 30) {
  const [data, setData] = useState<{ values: T; timestamp: number; frame_id: number } | null>(null)

  useEffect(() => {
    return subscribe(topic, type_name, rate_hz, (d) => {
      setData({ values: d.values as T, timestamp: d.timestamp, frame_id: d.frame_id })
    })
  }, [topic, type_name, rate_hz])

  return data
}

/** Fire a payload-less runtime event (a verb) on an events channel. */
export function ringEvent(channel: string, event_id: number) {
  ensureConnection()
  send({ type: 'ring-event', channel, event_id })
}

function subscribeEvents(channel: string, cb: (event_id: number) => void) {
  if (!eventListeners.has(channel)) eventListeners.set(channel, new Set())
  const cbs = eventListeners.get(channel)!
  const first = cbs.size === 0
  cbs.add(cb)
  ensureConnection()
  if (first) send({ type: 'listen-event', channel })

  return () => {
    const next = eventListeners.get(channel)
    if (!next) return
    next.delete(cb)
    if (next.size === 0) {
      eventListeners.delete(channel)
      send({ type: 'unlisten-event', channel })
    }
  }
}

/** Rolling feed of events fired on a channel since the page subscribed. */
export function useEventFeed(channel: string, max = 12) {
  const [feed, setFeed] = useState<{ event_id: number; at: number }[]>([])

  useEffect(() => {
    return subscribeEvents(channel, (event_id) => {
      setFeed((prev) => [{ event_id, at: Date.now() }, ...prev].slice(0, max))
    })
  }, [channel, max])

  return feed
}

export function useNatsSubject<T = unknown>(subject: string) {
  const [data, setData] = useState<T | null>(null)

  useEffect(() => {
    return subscribeNats(subject, (payload) => setData(payload as T))
  }, [subject])

  return data
}

export function usePublish() {
  return useCallback((subject: string, payload: Record<string, unknown> = {}) => {
    ensureConnection()
    send({ type: 'nats-publish', subject, payload })
  }, [])
}
