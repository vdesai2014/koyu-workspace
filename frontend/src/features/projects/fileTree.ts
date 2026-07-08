import type { FileListEntry } from './types'

export interface FileTreeNode {
  name: string
  path: string
  type: 'file' | 'folder'
  children: FileTreeNode[]
  file?: FileListEntry
}

export function buildFileTree(files: Record<string, FileListEntry>): FileTreeNode[] {
  function sortNodes(nodes: FileTreeNode[]): FileTreeNode[] {
    return [...nodes]
      .sort((left, right) => {
        if (left.type !== right.type) {
          return left.type === 'folder' ? -1 : 1
        }
        return left.name.localeCompare(right.name)
      })
      .map((node) => ({
        ...node,
        children: sortNodes(node.children),
      }))
  }

  const normalized: FileTreeNode[] = []
  for (const [path, file] of Object.entries(files)) {
    const parts = path.split('/')
    let cursor = normalized
    let currentPath = ''

    parts.forEach((part, index) => {
      currentPath = currentPath ? `${currentPath}/${part}` : part
      const isFile = index === parts.length - 1
      let node = cursor.find((candidate) => candidate.name === part)

      if (!node) {
        node = {
          name: part,
          path: currentPath,
          type: isFile ? 'file' : 'folder',
          children: [],
          file: isFile ? file : undefined,
        }
        cursor.push(node)
      }

      if (isFile) {
        node.file = file
      } else {
        cursor = node.children
      }
    })
  }

  return sortNodes(normalized)
}
