import { Navigate, useParams } from 'react-router-dom'

/** Redirect a legacy parameterised path to its new home, forwarding params. */
export default function LegacyRedirect({
  to,
}: {
  to: (p: Record<string, string>) => string
}) {
  const params = useParams()
  return <Navigate to={to(params as Record<string, string>)} replace />
}
