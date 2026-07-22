import { useEffect, useRef, useState } from 'react'
import { EditorContent, useEditor } from '@tiptap/react'
import StarterKit from '@tiptap/starter-kit'
import Placeholder from '@tiptap/extension-placeholder'
import Image from '@tiptap/extension-image'
import { Table } from '@tiptap/extension-table'
import { TableRow } from '@tiptap/extension-table-row'
import { TableCell } from '@tiptap/extension-table-cell'
import { TableHeader } from '@tiptap/extension-table-header'
import { marked } from 'marked'
import TurndownService from 'turndown'
// @ts-expect-error — turndown-plugin-gfm ships no types
import * as turndownGfm from 'turndown-plugin-gfm'

import { ReadmeEditorToolbar } from './ReadmeEditorToolbar'
import { preprocessMarkdownEmbeds, serializeDatasetDirective, serializeVideoDirective } from '../editorEmbeds'
import { ManifestEmbed } from '../extensions/ManifestEmbed'
import { VideoEmbed } from '../extensions/VideoEmbed'
import { ManifestViewerModal } from './ManifestViewerModal'

const turndown = new TurndownService({
  bulletListMarker: '-',
  codeBlockStyle: 'fenced',
  headingStyle: 'atx',
})

turndown.addRule('manifestEmbed', {
  filter: (node) => node.nodeName === 'DIV' && (node as HTMLElement).dataset.koyuEmbed === 'dataset',
  replacement: (_content, node) => {
    const manifestId = (node as HTMLElement).dataset.manifestId ?? ''
    return `\n\n${serializeDatasetDirective(manifestId)}\n\n`
  },
})

turndown.addRule('videoEmbed', {
  filter: (node) => node.nodeName === 'DIV' && (node as HTMLElement).dataset.koyuEmbed === 'video',
  replacement: (_content, node) => {
    const element = node as HTMLElement
    const manifestId = element.dataset.manifestId ?? ''
    const episodeId = element.dataset.episodeId ?? ''
    const camera = element.dataset.camera ?? ''
    return `\n\n${serializeVideoDirective(manifestId, episodeId, camera)}\n\n`
  },
})

turndown.use(turndownGfm.tables)

marked.setOptions({
  // breaks stays off so hard-wrapped README sources flow into paragraphs;
  // editor Shift+Enter breaks survive as trailing-two-space markdown.
  breaks: false,
  gfm: true,
})

function markdownToHtml(markdown: string) {
  return marked.parse(preprocessMarkdownEmbeds(markdown)) as string
}

function htmlToMarkdown(html: string) {
  return turndown.turndown(html).trimEnd()
}

interface MarkdownReadmeEditorProps {
  value: string
  editable: boolean
  placeholder?: string
  onChange: (markdown: string) => void
}

export function MarkdownReadmeEditor({
  value,
  editable,
  placeholder = 'Write README.md here…',
  onChange,
}: MarkdownReadmeEditorProps) {
  const lastAppliedValue = useRef(value)
  const [selectedManifestId, setSelectedManifestId] = useState<string | null>(null)

  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit.configure({
        codeBlock: {
          HTMLAttributes: {
            spellcheck: 'false',
          },
        },
      }),
      Placeholder.configure({
        placeholder,
      }),
      Image.configure({
        allowBase64: true,
        inline: false,
      }),
      Table.configure({
        resizable: false,
        HTMLAttributes: { class: 'project-readme-table' },
      }),
      TableRow,
      TableHeader,
      TableCell,
      ManifestEmbed,
      VideoEmbed,
    ],
    content: markdownToHtml(value),
    editable,
    editorProps: {
      attributes: {
        class: 'project-readme-tiptap',
      },
    },
    onUpdate: ({ editor: currentEditor }) => {
      const nextMarkdown = htmlToMarkdown(currentEditor.getHTML())
      lastAppliedValue.current = nextMarkdown
      onChange(nextMarkdown)
    },
  })

  useEffect(() => {
    if (!editor) return
    editor.setEditable(editable)
  }, [editor, editable])

  useEffect(() => {
    if (!editor) return
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const storage = editor.storage as any
    storage.manifestEmbed.onOpenViewer = (manifestId: string) => {
      setSelectedManifestId(manifestId)
    }
  }, [editor])

  useEffect(() => {
    if (!editor) return
    if (value === lastAppliedValue.current) return
    lastAppliedValue.current = value
    editor.commands.setContent(markdownToHtml(value), {
      emitUpdate: false,
    })
  }, [editor, value])

  if (!editor) {
    return <div className="project-readme-loading">Loading editor…</div>
  }

  return (
    <>
      <div className="project-readme-editor-shell">
        {editable ? <ReadmeEditorToolbar editor={editor} /> : null}
        <EditorContent editor={editor} />
      </div>
      {selectedManifestId ? <ManifestViewerModal manifestId={selectedManifestId} onClose={() => setSelectedManifestId(null)} /> : null}
    </>
  )
}
