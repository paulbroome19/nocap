import { Card, RowLink } from '../components/ui'

// The three entity-anchored reference tables. This list is the seam for future
// reference areas — one more RowLink adds a table, nothing else.
const SECTIONS = [
  {
    to: '/reference/entities',
    title: 'Entity Setup',
    subtitle: 'Reporting entities — name, LEI, country, scope',
  },
  {
    to: '/reference/filing-indicators',
    title: 'Filing Indicators',
    subtitle: 'Per entity + suite: which templates are required, optional, or not required',
  },
  {
    to: '/reference/parameters',
    title: 'Parameters',
    subtitle: 'Per entity + suite: reporting currency and decimals',
  },
]

export default function ReferenceData() {
  return (
    <section>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight text-slate-900">
        Reference Data
      </h1>
      <Card className="divide-y divide-slate-100">
        {SECTIONS.map((s) => (
          <RowLink key={s.to} to={s.to} title={s.title} subtitle={s.subtitle} />
        ))}
      </Card>
    </section>
  )
}
