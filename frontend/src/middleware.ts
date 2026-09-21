import { NextResponse, type NextRequest } from 'next/server'

/**
 * Server components cannot read the current path, and the guard needs it to send someone back where
 * they were going after signing in. This is the only reason middleware exists here — it makes no
 * session decisions, because the session store lives in the Node runtime and this does not.
 */
export function middleware(request: NextRequest) {
  const headers = new Headers(request.headers)
  headers.set('x-pathname', `${request.nextUrl.pathname}${request.nextUrl.search}`)
  return NextResponse.next({ request: { headers } })
}

export const config = {
  matcher: ['/((?!_next/static|_next/image|favicon.ico).*)'],
}
