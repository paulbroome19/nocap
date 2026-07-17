import { Link } from 'react-router-dom'

export default function Runs() {
  return (
    <section>
      <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
      <p className="mt-1 text-sm text-slate-500">
        Runs belong to a workflow. Open a workflow to start a new run or browse
        its history.
      </p>

      <div className="mt-8 rounded-lg border border-dashed border-slate-300 bg-white px-6 py-16 text-center">
        <p className="text-sm text-slate-400">
          Go to{' '}
          <Link to="/workflows" className="text-slate-600 underline">
            Workflows
          </Link>{' '}
          to select a suite and run it.
        </p>
      </div>
    </section>
  )
}
