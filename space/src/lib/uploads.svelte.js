// Files a visitor opens stay in this tab; nothing is sent anywhere.
import { parseFiles } from './convert.js'
import { go } from './router.svelte.js'

export const uploads = $state({ articles: [], records: [], error: null })
let counter = 0

export async function openFiles(fileList) {
  uploads.error = null
  try {
    const files = await Promise.all([...fileList].map(async (f) => ({ name: f.name, text: await f.text() })))
    const { articles, records } = parseFiles(files)
    for (const a of articles) uploads.articles.push({ ...a, key: `upload-${++counter}` })
    for (const r of records) uploads.records.push({ ...r, key: `upload-${++counter}` })
    if (records.length) go('records', uploads.records.at(-records.length).key)
    else if (articles.length) go('articles', uploads.articles.at(-articles.length).key)
    else uploads.error = 'No FHIR resources or extraction records were found in that file.'
  } catch (e) {
    uploads.error = e.message
  }
}
