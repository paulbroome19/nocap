import { Card, RowLink } from '../components/ui'

// Settings sections. This list is the seam for future settings areas — one more
// RowLink adds a section, nothing else.
const SECTIONS = [
  {
    to: '/settings/reporting',
    title: 'Reporting',
    subtitle: 'Active suites and their categories, per regulator',
  },
]

export default function Settings() {
  return (
    <section>
      <h1 className="mb-6 text-2xl font-semibold tracking-tight text-slate-900">
        Settings
      </h1>
      <Card className="divide-y divide-slate-100">
        {SECTIONS.map((s) => (
          <RowLink key={s.to} to={s.to} title={s.title} subtitle={s.subtitle} />
        ))}
      </Card>
    </section>
  )
}
