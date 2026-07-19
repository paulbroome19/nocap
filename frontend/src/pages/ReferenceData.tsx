import { Block, PageHeader, RowLink, SectionLabel } from '../components/ui'

// The three entity-anchored reference tables.
const SECTIONS = [
  {
    to: '/reference/entities',
    title: 'Entity Setup',
    subtitle: 'Reporting entities — name, LEI, country, scope',
  },
  {
    to: '/reference/filing-indicators',
    title: 'Filing Indicators',
    subtitle: 'Per entity and suite: which templates are required, optional, or not required',
  },
  {
    to: '/reference/parameters',
    title: 'Parameters',
    subtitle: 'Per entity and suite: reporting currency and decimals',
  },
]

export default function ReferenceData() {
  return (
    <section>
      <PageHeader title="Reference Data" />
      <SectionLabel>Tables</SectionLabel>
      <Block>
        {SECTIONS.map((s) => (
          <RowLink key={s.to} to={s.to} title={s.title} subtitle={s.subtitle} />
        ))}
      </Block>
    </section>
  )
}
