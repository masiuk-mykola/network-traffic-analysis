import * as z from 'zod'

// The API declares these limits; matching them here means an attempt that could only be refused
// never leaves the browser, and never costs one of the five the rate limiter allows per minute.
const EMAIL_MAX = 254
const PASSWORD_MAX = 256

export const credentialsSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, 'Enter your email')
    .max(EMAIL_MAX, 'That email is too long')
    .pipe(z.email('That does not look like an email')),
  password: z.string().min(1, 'Enter your password').max(PASSWORD_MAX, 'That password is too long'),
})

export type Credentials = z.infer<typeof credentialsSchema>
