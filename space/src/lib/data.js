// Loads the site's data files (plain or gzipped JSON) once each.
const cache = new Map()

export async function decode(bytes) {
  if (bytes[0] === 0x1f && bytes[1] === 0x8b) {
    const stream = new Blob([bytes]).stream().pipeThrough(new DecompressionStream('gzip'))
    return new Response(stream).text()
  }
  return new TextDecoder().decode(bytes)
}

export function load(path) {
  if (!cache.has(path)) {
    cache.set(path, fetch(`./data/${path}`).then(async (response) => {
      if (!response.ok) throw new Error(`Could not load ${path} (${response.status})`)
      return JSON.parse(await decode(new Uint8Array(await response.arrayBuffer())))
    }))
  }
  return cache.get(path)
}

export const loadIndex = () => load('index.json')
export const loadArticle = (id) => load(`articles/${id}.json.gz`)
export const loadRecord = (id) => load(`records/${id}.json.gz`)
export const loadTour = () => load('tour.json.gz')
