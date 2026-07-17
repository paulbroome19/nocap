type Props = {
  title: string
  description: string
}

/** Shared empty-state header for the scaffold pages. No business logic yet. */
export default function PagePlaceholder({ title, description }: Props) {
  return (
    <section>
      <h1 className="text-2xl font-semibold tracking-tight">{title}</h1>
      <p className="mt-1 text-sm text-slate-500">{description}</p>

      <div className="mt-8 rounded-lg border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
        <p className="text-sm text-slate-400">Nothing here yet.</p>
      </div>
    </section>
  )
}
