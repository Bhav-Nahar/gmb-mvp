import { Suspense } from 'react'
import LoginSuccessClient from './LoginSuccessClient'
import { RefreshCw } from 'lucide-react'

export default function LoginSuccessPage() {
  return (
    <Suspense fallback={
      <div className="flex h-screen w-screen items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-4 text-center p-6 max-w-sm glass-panel border border-border rounded-2xl shadow-2xl">
          <RefreshCw className="h-6 w-6 text-indigo-500 animate-spin" />
        </div>
      </div>
    }>
      <LoginSuccessClient />
    </Suspense>
  )
}
