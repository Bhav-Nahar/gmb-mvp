const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

interface RequestOptions extends RequestInit {
  params?: Record<string, string>
  _retry?: boolean
}

let refreshPromise: Promise<boolean> | null = null

async function refreshSession(): Promise<boolean> {
  if (refreshPromise) {
    return refreshPromise
  }
  
  refreshPromise = (async () => {
    try {
      const headers: Record<string, string> = {
        'Accept': 'application/json',
        'Content-Type': 'application/json'
      }
      
      const csrfToken = getCookie('gmb_csrf_token')
      if (csrfToken) {
        headers['X-CSRF-Token'] = csrfToken
      }

      const response = await fetch(`${API_BASE_URL}/auth/refresh`, {
        method: 'POST',
        credentials: 'include',
        headers
      })
      if (response.ok) {
        // The refresh response sets a new gmb_csrf_token via Set-Cookie.
        // Read it from the JSON body (backend returns it explicitly) so we
        // don't race against the browser applying the Set-Cookie header.
        try {
          const data = await response.json()
          if (data?.csrf_token && typeof document !== 'undefined') {
            document.cookie = `gmb_csrf_token=${data.csrf_token}; path=/; SameSite=None; Secure`
          }
        } catch (_) {}
        return true
      }
      return false
    } catch (e) {
      return false
    } finally {
      refreshPromise = null
    }
  })()
  
  return refreshPromise
}

function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const matches = document.cookie.match(new RegExp(
    "(?:^|; )" + name.replace(/([\.$?*|{}\(\)\[\]\\\/\+^])/g, '\\$1') + "=([^;]*)"
  ))
  return matches ? decodeURIComponent(matches[1]) : null
}

function isPublicPath(path: string): boolean {
  return path === '/login' || path.startsWith('/invite/') || path === '/login/success' || path === '/'
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')
  
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
  }

  // Inject CSRF Token on all mutating requests
  const method = options.method?.toUpperCase() || 'GET'
  if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(method)) {
    const csrfToken = getCookie('gmb_csrf_token')
    if (csrfToken) {
      headers.set('X-CSRF-Token', csrfToken)
    } else {
      console.warn(`[API] CSRF token missing for ${method} request to ${endpoint}. Available cookies: ${typeof document !== 'undefined' ? document.cookie : 'N/A'}`)
    }
  }

  let url = `${API_BASE_URL}${endpoint}`
  if (options.params) {
    const searchParams = new URLSearchParams(options.params)
    url += `?${searchParams.toString()}`
  }

  const config: RequestInit = {
    credentials: 'include',
    ...options,
    headers,
  }

  try {
    const response = await fetch(url, config)
    
    // Transparently refresh token for any 401 except for the refresh endpoint itself
    if (response.status === 401 && endpoint !== '/auth/refresh' && !options._retry) {
      const refreshed = await refreshSession()
      if (refreshed) {
        // Retry the original request exactly once
        return await request<T>(endpoint, { ...options, _retry: true })
      }
      
      if (typeof window !== 'undefined') {
        if (!isPublicPath(window.location.pathname)) {
          window.location.href = '/login?expired=true'
        }
      }
      throw new Error('Unauthorized session expired')
    }

    if (response.status === 401 && endpoint === '/auth/refresh') {
      if (typeof window !== 'undefined') {
        if (!isPublicPath(window.location.pathname)) {
          window.location.href = '/login?expired=true'
        }
      }
      throw new Error('Unauthorized session expired')
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      let errorMessage = 'An unexpected error occurred'
      
      if (typeof errorData.detail === 'string') {
        errorMessage = errorData.detail
      } else if (Array.isArray(errorData.detail)) {
        // Handle FastAPI validation errors
        errorMessage = errorData.detail.map((err: any) => `${err.loc?.join('.') || 'error'}: ${err.msg}`).join(', ')
      } else if (errorData.detail && typeof errorData.detail === 'object') {
        errorMessage = JSON.stringify(errorData.detail)
      } else if (errorData.message) {
        errorMessage = errorData.message
      }
      
      if (response.status === 402 && typeof window !== 'undefined') {
        const event = new CustomEvent('billing-error-402', { detail: { detail: errorMessage } })
        window.dispatchEvent(event)
      }

      throw new Error(errorMessage)
    }

    // Return empty object on 204 or empty response
    if (response.status === 204) {
      return {} as T
    }

    return await response.json()
  } catch (error: any) {
    console.error('API Request Error:', error.message)
    throw error
  }
}

export const api = {
  get: <T>(endpoint: string, params?: Record<string, string>, options?: RequestInit) => 
    request<T>(endpoint, { method: 'GET', params, ...options }),
    
  post: <T>(endpoint: string, body?: any, options?: RequestInit) => 
    request<T>(endpoint, { 
      method: 'POST', 
      body: body instanceof FormData ? body : JSON.stringify(body), 
      ...options 
    }),
    
  put: <T>(endpoint: string, body?: any, options?: RequestInit) => 
    request<T>(endpoint, { 
      method: 'PUT', 
      body: body instanceof FormData ? body : JSON.stringify(body), 
      ...options 
    }),
    
  patch: <T>(endpoint: string, body?: any, options?: RequestInit) =>
    request<T>(endpoint, {
      method: 'PATCH',
      body: body instanceof FormData ? body : JSON.stringify(body),
      ...options
    }),

  delete: <T>(endpoint: string, options?: RequestInit) => 
    request<T>(endpoint, { method: 'DELETE', ...options }),
}
