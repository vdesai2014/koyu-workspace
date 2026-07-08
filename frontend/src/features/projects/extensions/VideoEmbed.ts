import { Node, mergeAttributes, ReactNodeViewRenderer } from '@tiptap/react'

import { VideoEmbedBlock } from '../components/VideoEmbedBlock'

export const VideoEmbed = Node.create({
  name: 'videoEmbed',
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
      episodeId: {
        default: '',
        parseHTML: (element: HTMLElement) => element.getAttribute('data-episode-id') ?? '',
        renderHTML: (attributes: { episodeId: string }) => ({ 'data-episode-id': attributes.episodeId }),
      },
      camera: {
        default: '',
        parseHTML: (element: HTMLElement) => element.getAttribute('data-camera') ?? '',
        renderHTML: (attributes: { camera: string }) => ({ 'data-camera': attributes.camera }),
      },
    }
  },

  parseHTML() {
    return [{ tag: 'div[data-koyu-embed="video"]' }]
  },

  renderHTML({ HTMLAttributes }) {
    return ['div', mergeAttributes(HTMLAttributes, { 'data-koyu-embed': 'video' })]
  },

  addNodeView() {
    return ReactNodeViewRenderer(VideoEmbedBlock)
  },
})
