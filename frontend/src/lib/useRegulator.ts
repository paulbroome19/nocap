import { useEffect, useState } from 'react'
import { listRegulators, type Regulator } from '../api/snapshots'

// The reporting surfaces sit under a regulator (v1 is EBA-only). The list is
// small and stable, so cache it module-wide and hand back the primary one for
// breadcrumbs on pages whose URL doesn't carry the regulator.
let cache: Regulator[] | null = null

export function usePrimaryRegulator(): Regulator | null {
  const [regulator, setRegulator] = useState<Regulator | null>(cache?.[0] ?? null)
  useEffect(() => {
    if (cache) {
      setRegulator(cache[0] ?? null)
      return
    }
    listRegulators()
      .then((rs) => {
        cache = rs
        setRegulator(rs[0] ?? null)
      })
      .catch(() => {})
  }, [])
  return regulator
}
