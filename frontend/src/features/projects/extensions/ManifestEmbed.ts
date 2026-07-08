import { Node, mergeAttributes, ReactNodeViewRenderer } from '@tiptap/react'

import { ManifestEmbedCard } from '../components/ManifestEmbedCard'

export const ManifestEmbed = Node.create({
  name: 'manifestEmbed',
  group: 'block',
  atom: true,
  selectable: true,

  addAttributes() {
    return {
      manifestId: {
        default: '',
        parseHTML: (element: HTMLElement) => element.getAttribute('data-manifest-id') ?? '',
        renderHTML: (attributes: { manifestId: string }) => ({ 'data-manifest-id': attributes.manifestId }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-koyu-embed="dataset"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-koyu-embed': 'dataset' })]
  },

  addStorage() {
    return {
      onOpenViewer: null as ((manifestId: string) => void) | null,
    }
  },

  addNodeView() {
    return ReactNodeViewRenderer(ManifestEmbedCard)
  },
})
