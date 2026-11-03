// Filters for the article list and the cohort builder. Every one reads the model's extraction: age at
// presentation and documented sex (as groups), and the kinds of facts it found in each article.
// Age ranges from the model's age at presentation (scripts/build_data.py assigns them).
export const AGES = ['Under 1 year', '1–17 years', '18–39 years', '40–64 years', '65–79 years', '80 years and over']
const IN_RECORD = ['Serial measurements', 'Imaging', 'Pathology', 'Microbiology', 'Vital signs', 'Clinical scores', 'Genetic testing']
const IN_ARTICLE = ['Several patients', 'Figures']

// count(value) says how many items a choice would keep; choices that keep none are left out.
export function ageOptions(count) {
  return [{ value: '', label: 'Any age' }, ...AGES.map((g) => ({ value: g, label: g, count: count(g) })).filter((o) => o.count)]
}

export function sexOptions(count) {
  return [{ value: '', label: 'Any sex' }, ...['Female', 'Male'].map((x) => ({ value: x, label: x, count: count(x) })).filter((o) => o.count)]
}

export function themeOptions(count) {
  const group = (label, names) => {
    const items = names.map((t) => ({ value: t, label: t, count: count(t), indent: true })).filter((o) => o.count)
    return items.length ? [{ group: true, label }, ...items] : []
  }
  return [{ value: '', label: 'Any theme' }, ...group('In the record', IN_RECORD), ...group('In the article', IN_ARTICLE)]
}
