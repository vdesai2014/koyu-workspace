import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'

import { Breadcrumbs } from '../../components/ui/Breadcrumbs'
import { fetchDatasetManifest } from './api'
import { DatasetViewer } from './DatasetViewer'

export function DatasetDetailPage() {
  const { manifestId = '' } = useParams()
  const [manifestName, setManifestName] = useState(manifestId)

  useEffect(() => {
    let cancelled = false

    async function loadManifestName() {
      if (!manifestId) {
        setManifestName('')
        return
      }
      try {
        const manifest = await fetchDatasetManifest(manifestId)
        if (!cancelled) {
          setManifestName(manifest.name || manifestId)
        }
      } catch {
        if (!cancelled) {
          setManifestName(manifestId)
        }
      }
    }

    void loadManifestName()
    return () => {
      cancelled = true
    }
  }, [manifestId])

  return (
    <section className="coupon-page">
      <div className="coupon-shell">
        <Breadcrumbs
          crumbs={[
            { label: 'Datasets', href: '/datasets' },
            { label: manifestName || manifestId },
          ]}
        />
        <DatasetViewer manifestId={manifestId} />
      </div>
    </section>
  )
}
