import type { Editor } from '@tiptap/react'

interface ReadmeEditorToolbarProps {
  editor: Editor
}

interface ToolbarButton {
  label: string
  icon: string
  action: () => void
  isActive?: () => boolean
}

export function ReadmeEditorToolbar({ editor }: ReadmeEditorToolbarProps) {
  const buttons: (ToolbarButton | 'divider')[] = [
    {
      label: 'Bold',
      icon: 'B',
      action: () => editor.chain().focus().toggleBold().run(),
      isActive: () => editor.isActive('bold'),
    },
    {
      label: 'Italic',
      icon: 'I',
      action: () => editor.chain().focus().toggleItalic().run(),
      isActive: () => editor.isActive('italic'),
    },
    {
      label: 'Strikethrough',
      icon: 'S',
      action: () => editor.chain().focus().toggleStrike().run(),
      isActive: () => editor.isActive('strike'),
    },
    {
      label: 'Inline code',
      icon: '<>',
      action: () => editor.chain().focus().toggleCode().run(),
      isActive: () => editor.isActive('code'),
    },
    'divider',
    {
      label: 'Paragraph',
      icon: 'P',
      action: () => editor.chain().focus().setParagraph().run(),
      isActive: () => editor.isActive('paragraph'),
    },
    {
      label: 'Heading 1',
      icon: 'H1',
      action: () => editor.chain().focus().toggleHeading({ level: 1 }).run(),
      isActive: () => editor.isActive('heading', { level: 1 }),
    },
    {
      label: 'Heading 2',
      icon: 'H2',
      action: () => editor.chain().focus().toggleHeading({ level: 2 }).run(),
      isActive: () => editor.isActive('heading', { level: 2 }),
    },
    {
      label: 'Heading 3',
      icon: 'H3',
      action: () => editor.chain().focus().toggleHeading({ level: 3 }).run(),
      isActive: () => editor.isActive('heading', { level: 3 }),
    },
    'divider',
    {
      label: 'Bullet list',
      icon: '•',
      action: () => editor.chain().focus().toggleBulletList().run(),
      isActive: () => editor.isActive('bulletList'),
    },
    {
      label: 'Ordered list',
      icon: '1.',
      action: () => editor.chain().focus().toggleOrderedList().run(),
      isActive: () => editor.isActive('orderedList'),
    },
    {
      label: 'Blockquote',
      icon: '“',
      action: () => editor.chain().focus().toggleBlockquote().run(),
      isActive: () => editor.isActive('blockquote'),
    },
    {
      label: 'Code block',
      icon: '{}',
      action: () => editor.chain().focus().toggleCodeBlock().run(),
      isActive: () => editor.isActive('codeBlock'),
    },
    'divider',
    {
      label: 'Divider',
      icon: '—',
      action: () => editor.chain().focus().setHorizontalRule().run(),
    },
  ]

  return (
    <div className="editor-toolbar">
      {buttons.map((button, index) => {
        if (button === 'divider') {
          return <div key={`divider-${index}`} className="toolbar-divider" />
        }

        return (
          <button
            key={button.label}
            type="button"
            className={`toolbar-btn${button.isActive?.() ? ' active' : ''}`}
            title={button.label}
            aria-label={button.label}
            onClick={button.action}
          >
            {button.icon}
          </button>
        )
      })}
    </div>
  )
}
