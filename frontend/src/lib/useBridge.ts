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
