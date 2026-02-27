import type { ReactNode } from 'react'

interface MarkdownMessageProps {
  content: string
}

function parseInline(text: string): ReactNode[] {
  const nodes: ReactNode[] = []
  const pattern = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g
  let lastIndex = 0
  let key = 0

  for (const match of text.matchAll(pattern)) {
    const index = match.index ?? 0
    if (index > lastIndex) {
      nodes.push(text.slice(lastIndex, index))
    }
    const token = match[0]
    if (token.startsWith('`') && token.endsWith('`')) {
      nodes.push(
        <code
          key={`code-${key++}`}
          className="px-1 py-0.5 rounded bg-gray-900/80 text-emerald-300 text-[0.85em]"
        >
          {token.slice(1, -1)}
        </code>,
      )
    } else if (token.startsWith('**') && token.endsWith('**')) {
      nodes.push(
        <strong key={`strong-${key++}`} className="font-semibold text-gray-100">
          {token.slice(2, -2)}
        </strong>,
      )
    } else if (token.startsWith('*') && token.endsWith('*')) {
      nodes.push(
        <em key={`em-${key++}`} className="italic">
          {token.slice(1, -1)}
        </em>,
      )
    } else if (token.startsWith('[') && token.includes('](') && token.endsWith(')')) {
      const split = token.indexOf('](')
      const label = token.slice(1, split)
      const href = token.slice(split + 2, -1)
      nodes.push(
        <a
          key={`link-${key++}`}
          href={href}
          target="_blank"
          rel="noreferrer"
          className="text-blue-300 hover:text-blue-200 underline underline-offset-2"
        >
          {label}
        </a>,
      )
    } else {
      nodes.push(token)
    }
    lastIndex = index + token.length
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex))
  }

  return nodes
}

function isBlockStart(line: string): boolean {
  const trimmed = line.trim()
  return (
    trimmed.startsWith('#') ||
    trimmed.startsWith('- ') ||
    trimmed.startsWith('* ') ||
    /^\d+\.\s+/.test(trimmed) ||
    trimmed.startsWith('> ') ||
    trimmed.startsWith('```')
  )
}

export default function MarkdownMessage({ content }: MarkdownMessageProps) {
  const lines = content.replace(/\r\n/g, '\n').split('\n')
  const blocks: ReactNode[] = []
  let i = 0

  while (i < lines.length) {
    const line = lines[i]
    const trimmed = line.trim()

    if (!trimmed) {
      i += 1
      continue
    }

    if (trimmed.startsWith('```')) {
      const codeLines: string[] = []
      i += 1
      while (i < lines.length && !lines[i].trim().startsWith('```')) {
        codeLines.push(lines[i])
        i += 1
      }
      if (i < lines.length) {
        i += 1
      }
      blocks.push(
        <pre
          key={`codeblock-${i}`}
          className="bg-gray-900/80 border border-gray-700 rounded-lg px-3 py-2 overflow-x-auto text-[12px] text-emerald-300"
        >
          <code>{codeLines.join('\n')}</code>
        </pre>,
      )
      continue
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/)
    if (heading) {
      const level = heading[1].length
      const title = heading[2]
      const sizeClass =
        level <= 2 ? 'text-base font-semibold text-gray-100' : 'text-sm font-semibold text-gray-200'
      blocks.push(
        <div key={`heading-${i}`} className={sizeClass}>
          {parseInline(title)}
        </div>,
      )
      i += 1
      continue
    }

    if (trimmed.startsWith('- ') || trimmed.startsWith('* ')) {
      const items: string[] = []
      while (i < lines.length) {
        const candidate = lines[i].trim()
        if (!(candidate.startsWith('- ') || candidate.startsWith('* '))) {
          break
        }
        items.push(candidate.slice(2))
        i += 1
      }
      blocks.push(
        <ul key={`ul-${i}`} className="list-disc pl-5 space-y-1">
          {items.map((item, idx) => (
            <li key={`ul-item-${i}-${idx}`}>{parseInline(item)}</li>
          ))}
        </ul>,
      )
      continue
    }

    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = []
      while (i < lines.length) {
        const candidate = lines[i].trim()
        if (!/^\d+\.\s+/.test(candidate)) {
          break
        }
        items.push(candidate.replace(/^\d+\.\s+/, ''))
        i += 1
      }
      blocks.push(
        <ol key={`ol-${i}`} className="list-decimal pl-5 space-y-1">
          {items.map((item, idx) => (
            <li key={`ol-item-${i}-${idx}`}>{parseInline(item)}</li>
          ))}
        </ol>,
      )
      continue
    }

    if (trimmed.startsWith('> ')) {
      const quoteLines: string[] = []
      while (i < lines.length && lines[i].trim().startsWith('> ')) {
        quoteLines.push(lines[i].trim().slice(2))
        i += 1
      }
      blocks.push(
        <blockquote
          key={`quote-${i}`}
          className="border-l-2 border-gray-600 pl-3 text-gray-300 italic"
        >
          {parseInline(quoteLines.join(' '))}
        </blockquote>,
      )
      continue
    }

    const paragraphLines: string[] = [trimmed]
    i += 1
    while (i < lines.length) {
      const next = lines[i]
      if (!next.trim() || isBlockStart(next)) {
        break
      }
      paragraphLines.push(next.trim())
      i += 1
    }
    blocks.push(
      <p key={`p-${i}`} className="text-gray-200 leading-relaxed">
        {parseInline(paragraphLines.join(' '))}
      </p>,
    )
  }

  if (blocks.length === 0) {
    return <div className="whitespace-pre-wrap">{content}</div>
  }

  return <div className="space-y-2">{blocks}</div>
}
