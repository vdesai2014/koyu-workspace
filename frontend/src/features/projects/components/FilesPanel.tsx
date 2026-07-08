import { useCallback, useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'

import { useAuth } from '../../auth/localAuth'
import { buildFileTree, type FileTreeNode } from '../fileTree'
import type { DownloadFilesResponse, FileListEntry } from '../types'
import { usePanelOpen, useScrollRestore, useTreeExpanded } from '../usePanelState'

const TEXT_EXTENSIONS = [
  '.txt', '.md', '.log', '.yaml', '.yml', '.json', '.csv', '.toml',
  '.py', '.sh', '.cfg', '.ini', '.xml', '.html', '.css', '.js', '.ts',
  '.tsx', '.jsx', '.sql', '.env', '.gitignore', '.dockerfile',
  '.rs', '.go', '.java', '.c', '.h', '.cpp', '.hpp', '.rb', '.lua',
]
const IMAGE_EXTENSIONS = ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp']

function isTextFile(name: string) {
  const lower = name.toLowerCase()
  return TEXT_EXTENSIONS.some((ext) => lower.endsWith(ext)) || !lower.includes('.')
}

function isImageFile(name: string) {
  const lower = name.toLowerCase()
  return IMAGE_EXTENSIONS.some((ext) => lower.endsWith(ext))
}

function isPreviewable(name: string) {
  return isTextFile(name) || isImageFile(name)
}

interface FilesPanelProps {
  entityName: string
  files: Record<string, FileListEntry>
  fetchDownloadUrls: (paths: string[], getToken: () => Promise<string | null>) => Promise<DownloadFilesResponse>
}

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

function FilePreviewModal({
  fileName,
  filePath,
  fileSize,
  fetchUrl,
  onClose,
}: {
  fileName: string
  filePath: string
  fileSize: number
  fetchUrl: () => Promise<string>
  onClose: () => void
}) {
  const [content, setContent] = useState<string | null>(null)
  const [imageUrl, setImageUrl] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const image = isImageFile(fileName)

  useEffect(() => {
    const handleKey = (event: KeyboardEvent) => { if (event.key === 'Escape') onClose() }
    document.addEventListener('keydown', handleKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', handleKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  useEffect(() => {
    let cancelled = false
    setLoading(true)

    fetchUrl()
      .then(async (url) => {
        if (cancelled) return
        if (image) {
          setImageUrl(url)
          setLoading(false)
        } else {
          const response = await fetch(url)
          if (!response.ok) throw new Error(`HTTP ${response.status}`)
          const text = await response.text()
          if (!cancelled) {
            setContent(text)
            setLoading(false)
          }
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(String(err))
          setLoading(false)
        }
      })

    return () => { cancelled = true }
  }, [fetchUrl, image])

  const ext = fileName.split('.').pop()?.toLowerCase() ?? ''

  return createPortal(
    <div className="file-preview-overlay" onClick={(event) => { if (event.target === event.currentTarget) onClose() }}>
      <div className="file-preview-modal">
        <div className="file-preview-header">
          <div className="file-preview-title">
            <strong>{fileName}</strong>
            <span>{filePath !== fileName ? filePath : ''}</span>
            <span>{formatBytes(fileSize)}</span>
          </div>
          <button type="button" className="file-preview-close" onClick={onClose}>&times;</button>
        </div>
        <div className="file-preview-body">
          {loading && <div className="file-preview-status">Loading...</div>}
          {error && <div className="file-preview-status file-preview-error">{error}</div>}
          {image && imageUrl ? (
            <div className="file-preview-image-wrap">
              <img src={imageUrl} alt={fileName} />
            </div>
          ) : null}
          {!image && content != null ? (
            <pre className={`file-preview-code${ext === 'md' ? ' is-markdown' : ''}`}>{content}</pre>
          ) : null}
        </div>
      </div>
    </div>,
    document.body,
  )
}

function FileTreeNodeRow({
  node,
  expanded,
  onToggle,
  onPreview,
}: {
  node: FileTreeNode
  expanded: Set<string>
  onToggle: (path: string) => void
  onPreview: (node: FileTreeNode) => void
}) {
  const isFolder = node.children.length > 0
  const open = isFolder && expanded.has(node.path)
  const canPreview = !isFolder && node.file && isPreviewable(node.name)

  function handleClick() {
    if (isFolder) {
      onToggle(node.path)
    } else if (canPreview) {
      onPreview(node)
    }
  }

  return (
    <li>
      <div
        className={`project-file-node${isFolder ? ' project-file-node-folder' : ''}${canPreview ? ' project-file-node-previewable' : ''}`}
        onClick={handleClick}
      >
        <div className="project-file-node-main">
          {isFolder ? (
            <span className="project-file-node-glyph" aria-hidden="true">{open ? '▾' : '▸'}</span>
          ) : (
            <span className="project-file-node-glyph" aria-hidden="true">·</span>
          )}
          <strong>{node.name}</strong>
          {isFolder ? <span className="project-file-node-count">{node.children.length}</span> : null}
          {canPreview ? <span className="project-file-node-hint">preview</span> : null}
        </div>
        {node.file ? <time>{formatBytes(node.file.size)}</time> : null}
      </div>
      {isFolder && open ? <FileTreeListInner nodes={node.children} expanded={expanded} onToggle={onToggle} onPreview={onPreview} /> : null}
    </li>
  )
}

function FileTreeListInner({
  nodes,
  expanded,
  onToggle,
  onPreview,
}: {
  nodes: FileTreeNode[]
  expanded: Set<string>
  onToggle: (path: string) => void
  onPreview: (node: FileTreeNode) => void
}) {
  if (nodes.length === 0) {
    return <p className="project-detail-empty">No files yet.</p>
  }

  return (
    <ul className="project-file-tree">
      {nodes.map((node) => (
        <FileTreeNodeRow key={node.path} node={node} expanded={expanded} onToggle={onToggle} onPreview={onPreview} />
      ))}
    </ul>
  )
}

export function FilesPanel({ entityName, files, fetchDownloadUrls }: FilesPanelProps) {
  const { getToken } = useAuth()
  const [previewNode, setPreviewNode] = useState<FileTreeNode | null>(null)
  const { isOpen: panelOpen, handleToggle: handlePanelToggle } = usePanelOpen(`files_${entityName}`)
  const { expanded, toggle: handleTreeToggle } = useTreeExpanded(`files_${entityName}`)
  const scrollRef = useScrollRestore(`files_${entityName}`)
  const fileTree = useMemo(() => buildFileTree(files), [files])
  const paths = useMemo(() => Object.keys(files).sort((left, right) => left.localeCompare(right)), [files])

  const fetchPreviewUrl = useCallback(async () => {
    if (!previewNode?.path) throw new Error('No file path')
    const response = await fetchDownloadUrls([previewNode.path], getToken)
    const url = response.urls[previewNode.path]
    if (!url) throw new Error('No download URL returned')
    return url
  }, [previewNode, fetchDownloadUrls, getToken])

  return (
    <details className="project-detail-panel" open={panelOpen} onToggle={handlePanelToggle}>
      <summary>
        <span>Files</span>
        <span className="project-panel-summary-right">
          <span>{paths.length}</span>
        </span>
      </summary>

      <div className="project-detail-panel-body">
        <div className="project-file-tree-scroll" ref={scrollRef}>
          <FileTreeListInner nodes={fileTree} expanded={expanded} onToggle={handleTreeToggle} onPreview={setPreviewNode} />
        </div>
      </div>

      {previewNode && previewNode.file ? (
        <FilePreviewModal
          fileName={previewNode.name}
          filePath={previewNode.path}
          fileSize={previewNode.file.size}
          fetchUrl={fetchPreviewUrl}
          onClose={() => setPreviewNode(null)}
        />
      ) : null}
    </details>
  )
}
