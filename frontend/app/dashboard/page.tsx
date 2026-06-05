import { Suspense } from 'react'
import DashboardClient from './DashboardClient'
import { RefreshCw } from 'lucide-react'

export default function DashboardPage() {
  return (
    <Suspense fallback={
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <RefreshCw className="h-8 w-8 text-indigo-500 animate-spin" />
      </div>
    }>
      <DashboardClient />
    </Suspense>
  )
}
