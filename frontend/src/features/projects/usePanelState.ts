import { useCallback, useEffect, useRef, useState } from 'react'

const PANEL_PREFIX = 'koyu_panel_'
const TREE_PREFIX = 'koyu_tree_'
const SCROLL_PREFIX = 'koyu_scroll_'

export function usePanelOpen(key: string, defaultOpen = true) {
  const storageKey = PANEL_PREFIX + key
  const [isOpen, setIsOpen] = useState(() => {
    const saved = localStorage.getItem(storageKey)
    return saved !== null ? saved === '1' : defaultOpen
  })

  const handleToggle = useCallback((event: React.SyntheticEvent<HTMLDetailsElement>) => {
    const open = (event.currentTarget as HTMLDetailsElement).open
    setIsOpen(open)
    localStorage.setItem(storageKey, open ? '1' : '0')
  }, [storageKey])

  return { isOpen, handleToggle }
}

export function useTreeExpanded(key: string) {
  const storageKey = TREE_PREFIX + key
  const [expanded, setExpanded] = useState<Set<string>>(() => {
    try {
      const raw = localStorage.getItem(storageKey)
      if (!raw) return new Set<string>()
      const parsed = JSON.parse(raw)
      return Array.isArray(parsed) ? new Set(parsed) : new Set<string>()
    } catch {
      return new Set<string>()
    }
  })

  const toggle = useCallback((path: string) => {
    setExpanded((previous) => {
      const next = new Set(previous)
      if (next.has(path)) {
        next.delete(path)
      } else {
        next.add(path)
      }
      localStorage.setItem(storageKey, JSON.stringify([...next]))
      return next
    })
  }, [storageKey])

  return { expanded, toggle }
}

export function useScrollRestore(key: string) {
  const storageKey = SCROLL_PREFIX + key
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    const saved = localStorage.getItem(storageKey)
    if (saved) {
      element.scrollTop = Number(saved)
    }
  }, [storageKey])

  useEffect(() => {
    const element = scrollRef.current
    if (!element) return
    let timer: ReturnType<typeof setTimeout>

    function handleScroll() {
      clearTimeout(timer)
      const current = scrollRef.current
      if (!current) return
      timer = setTimeout(() => {
        localStorage.setItem(storageKey, String(current.scrollTop))
      }, 150)
    }

    element.addEventListener('scroll', handleScroll)
    return () => {
      clearTimeout(timer)
      element.removeEventListener('scroll', handleScroll)
    }
  }, [storageKey])

  return scrollRef
}
