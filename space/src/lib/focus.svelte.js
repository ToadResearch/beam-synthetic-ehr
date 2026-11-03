// What the article should highlight: the fact under the pointer and the fact the reader pinned.
// Each is { id, color, evidence: [{ seg, quote }], cells: [cellId] }.
export const focus = $state({ hover: null, pinned: null, reveal: null })

export function pin(target, seg) {
  focus.pinned = target
  focus.reveal = target ? { seg: seg ?? target.evidence?.[0]?.seg ?? cellSegment(target.cells?.[0]), at: Date.now() } : null
}

export function cellSegment(cell) {
  return cell ? cell.replace(/-(c|h)\d+$/, '') : null
}
