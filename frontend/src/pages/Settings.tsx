import { Block, PageHeader, RowLink, SectionLabel } from '../components/ui'

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
      <PageHeader title="Settings" />
      <SectionLabel>Sections</SectionLabel>
      <Block>
        {SECTIONS.map((s) => (
          <RowLink key={s.to} to={s.to} title={s.title} subtitle={s.subtitle} />
        ))}
      </Block>
    </section>
  )
}
