/**
 * Every address this app owns, in one place. Screens and redirects name a route from here rather
 * than spelling one out, so renaming a screen is one edit and a typo is a type error.
 *
 * These are the app's own paths. The API's paths are not routes: they are built in `@api/keys` and
 * read through the proxy.
 */
export const ROUTES = {
  signIn: '/login',
  search: '/search',
  /** A session id is a uint64 as a string; it goes into the address exactly as it arrived. */
  session: (id: string) => `/sessions/${id}`,
} as const

/** Where someone lands when nothing else names a destination. */
export const DEFAULT_TARGET = ROUTES.search
