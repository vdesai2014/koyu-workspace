import type { RunSummary } from './types'

export interface RunTreeNode extends RunSummary {
  children: RunTreeNode[]
}

export function buildRunTree(runs: RunSummary[]): RunTreeNode[] {
  const nodes = new Map<string, RunTreeNode>()

  for (const run of runs) {
    nodes.set(run.id, { ...run, children: [] })
  }

  const roots: RunTreeNode[] = []
  for (const run of runs) {
    const node = nodes.get(run.id)
    if (!node) continue

    if (run.parent_id && nodes.has(run.parent_id)) {
      nodes.get(run.parent_id)?.children.push(node)
    } else {
      roots.push(node)
    }
  }

  return roots
}

export function countRunDescendants(node: RunTreeNode): number {
  return node.children.reduce((total, child) => total + 1 + countRunDescendants(child), 0)
}
