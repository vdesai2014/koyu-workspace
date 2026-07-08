import { useCallback, useMemo } from 'react'

export function useAuth() {
  const getToken = useCallback(async () => null as string | null, [])
  return useMemo(() => ({ getToken }), [getToken])
}

export function useUser() {
  const user = useMemo(() => ({
    id: 'local',
    username: 'local',
  }), [])
  return useMemo(() => ({ user }), [user])
}
