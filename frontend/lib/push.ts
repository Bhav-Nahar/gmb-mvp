import { api } from '@/lib/api'

function urlBase64ToUint8Array(base64String: string): Uint8Array {
  const padding = '='.repeat((4 - (base64String.length % 4)) % 4)
  const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = atob(base64)
  const out = new Uint8Array(raw.length)
  for (let i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i)
  return out
}

export function pushSupported(): boolean {
  return typeof window !== 'undefined' && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
}

/** Register SW, request permission, subscribe, and save to backend. Returns true on success. */
export async function enablePush(): Promise<boolean> {
  if (!pushSupported()) throw new Error('Push notifications are not supported in this browser.')

  const reg = await navigator.serviceWorker.register('/sw.js')
  await navigator.serviceWorker.ready

  const permission = await Notification.requestPermission()
  if (permission !== 'granted') throw new Error('Notification permission was not granted.')

  const { key } = await api.get<{ key: string }>('/push/vapid-public-key')

  let sub = await reg.pushManager.getSubscription()
  if (!sub) {
    sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(key) as BufferSource,
    })
  }

  await api.post('/push/subscribe', sub.toJSON())
  return true
}

export async function currentPushPermission(): Promise<NotificationPermission | 'unsupported'> {
  if (!pushSupported()) return 'unsupported'
  return Notification.permission
}

/** Whether this device currently has an active push subscription. */
export async function isPushSubscribed(): Promise<boolean> {
  if (!pushSupported()) return false
  try {
    const reg = await navigator.serviceWorker.getRegistration()
    if (!reg) return false
    return !!(await reg.pushManager.getSubscription())
  } catch {
    return false
  }
}

/** Remove this device's push subscription (browser + backend). Safe to call on
 * logout; never throws. Must run while the session is still authenticated so the
 * backend delete is accepted. */
export async function disablePush(): Promise<void> {
  if (!pushSupported()) return
  try {
    const reg = await navigator.serviceWorker.getRegistration()
    const sub = reg ? await reg.pushManager.getSubscription() : null
    if (!sub) return
    try { await api.post('/push/unsubscribe', sub.toJSON()) } catch { /* best effort */ }
    await sub.unsubscribe()
  } catch {
    /* ignore — logout must never be blocked by push cleanup */
  }
}
