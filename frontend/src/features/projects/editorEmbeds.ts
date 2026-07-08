const DIRECTIVE_PATTERN = /::(dataset|video)\{([^}]*)\}/g

type DirectiveType = 'dataset' | 'video'

function escapeHtml(value: string) {
  return value
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}

export function parseDirectiveAttributes(raw: string): Record<string, string> {
  const attrs: Record<string, string> = {}
  const attrPattern = /([a-zA-Z_][a-zA-Z0-9_-]*)="([^"]*)"/g
  for (const match of raw.matchAll(attrPattern)) {
    attrs[match[1]] = match[2]
  }
  return attrs
}

export function preprocessMarkdownEmbeds(markdown: string) {
  return markdown.replace(DIRECTIVE_PATTERN, (_, type: DirectiveType, rawAttrs: string) => {
    const attrs = parseDirectiveAttributes(rawAttrs)
    if (type === 'dataset' && attrs.manifest) {
      return `<div data-koyu-embed="dataset" data-manifest-id="${escapeHtml(attrs.manifest)}"></div>`
    }
    if (type === 'video' && attrs.manifest && attrs.episode && attrs.camera) {
      return `<div data-koyu-embed="video" data-manifest-id="${escapeHtml(attrs.manifest)}" data-episode-id="${escapeHtml(attrs.episode)}" data-camera="${escapeHtml(attrs.camera)}"></div>`
    }
    return ''
  })
}

export function serializeDatasetDirective(manifestId: string) {
  return `::dataset{manifest="${manifestId}"}`
}

export function serializeVideoDirective(manifestId: string, episodeId: string, camera: string) {
  return `::video{manifest="${manifestId}" episode="${episodeId}" camera="${camera}"}`
}
