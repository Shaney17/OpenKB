/** Avoid rendering OKF/YAML metadata as Markdown page content. A leading
 * thematic break followed by prose is preserved. */
function looksLikeYamlLine(line: string): boolean {
  if (line.trim() === '') return true
  if (/^[ \t]*#/.test(line)) return true
  if (/^[ \t]*-([ \t]|$)/.test(line)) return true
  if (/^[ \t]+\S/.test(line)) return true
  const m = /^[ \t]*[\w.-]+[ \t]*:([ \t]+(.*))?$/.exec(line)
  if (!m) return false
  const value = (m[2] ?? '').trim()
  if (value === '') return true
  if (/^["'[{]/.test(value)) return true
  return !/\s/.test(value)
}

export function stripFrontmatter(md: string): string {
  const m = /^---[ \t]*\r?\n([\s\S]*?)\r?\n---[ \t]*(?:\r?\n|$)/.exec(md)
  if (!m) return md
  if (!m[1].split(/\r?\n/).every(looksLikeYamlLine)) return md
  return md.slice(m[0].length)
}
