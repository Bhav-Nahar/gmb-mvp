import { Suspense } from 'react'
import LoginClient from './LoginClient'
import { RefreshCw } from 'lucide-react'

export default function LoginPage() {
  return (
    <Suspense fallback={
      <div className="flex min-h-screen items-center justify-center bg-background">
        <RefreshCw className="h-8 w-8 text-indigo-500 animate-spin" />
      </div>
    }>
      <LoginClient />
    </Suspense>
  )
}
