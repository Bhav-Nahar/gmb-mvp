const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000/api/v1'

interface RequestOptions extends RequestInit {
  params?: Record<string, string>
}

async function request<T>(endpoint: string, options: RequestOptions = {}): Promise<T> {
  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')
  
  if (!(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json')
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
    
    if (response.status === 401) {
      if (typeof window !== 'undefined') {
        localStorage.removeItem('gmb_logged_in')
        localStorage.removeItem('gmb_user')
        window.location.href = '/login?expired=true'
      }
      throw new Error('Unauthorized session expired')
    }

    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}))
      throw new Error(errorData.detail || 'An unexpected error occurred')
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
    
  delete: <T>(endpoint: string, options?: RequestInit) => 
    request<T>(endpoint, { method: 'DELETE', ...options }),
}
