import { Modal } from '../../../components/ui/Modal'
import { DatasetViewer } from '../../datasets/DatasetViewer'

export function ManifestViewerModal({ manifestId, onClose }: { manifestId: string; onClose: () => void }) {
  return (
    <Modal
      title="Dataset Viewer"
      onClose={onClose}
      panelClassName="modal-panel-wide modal-panel-dataset"
      bodyClassName="modal-body-dataset"
    >
      <DatasetViewer manifestId={manifestId} compact />
    </Modal>
  )
}
