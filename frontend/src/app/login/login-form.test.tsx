import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { LoginForm } from './login-form'

const replace = vi.fn()
vi.mock('next/navigation', () => ({
  useRouter: () => ({ replace, refresh: vi.fn() }),
}))

function renderForm() {
  const client = new QueryClient({ defaultOptions: { mutations: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <LoginForm />
    </QueryClientProvider>,
  )
}

function stubFetch(response: Response | (() => Promise<Response>)) {
  const spy = vi.fn(async () => (typeof response === 'function' ? response() : response))
  vi.stubGlobal('fetch', spy)
  return spy
}

beforeEach(() => {
  replace.mockClear()
})

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('LoginForm', () => {
  it('does not spend an attempt on empty fields', async () => {
    const spy = stubFetch(Response.json({}, { status: 200 }))
    renderForm()

    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('Enter your email')).toBeInTheDocument()
    expect(screen.getByText('Enter your password')).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })

  it('does not spend an attempt on something that cannot be an email', async () => {
    const spy = stubFetch(Response.json({}, { status: 200 }))
    renderForm()

    await userEvent.type(screen.getByLabelText('Email'), 'not-an-email')
    await userEvent.type(screen.getByLabelText('Password'), 'demo-analyst')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    expect(await screen.findByText('That does not look like an email')).toBeInTheDocument()
    expect(spy).not.toHaveBeenCalled()
  })

  it('cannot be submitted twice while an attempt is in flight', async () => {
    let release: (value: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => {
      release = resolve
    })
    const spy = stubFetch(() => pending)
    renderForm()

    await userEvent.type(screen.getByLabelText('Email'), 'ana@quillmere.example')
    await userEvent.type(screen.getByLabelText('Password'), 'demo-analyst')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    const button = await screen.findByRole('button', { name: /signing in/i })
    expect(button).toBeDisabled()
    await userEvent.click(button)
    expect(spy).toHaveBeenCalledOnce()

    release(Response.json({ user: { display_name: 'Ana' } }, { status: 200 }))
  })

  it('reports a rejected pair without saying whether the email exists', async () => {
    stubFetch(
      Response.json(
        { code: 'invalid_credentials', detail: 'Unknown email or wrong password.' },
        { status: 401 },
      ),
    )
    renderForm()

    await userEvent.type(screen.getByLabelText('Email'), 'ana@quillmere.example')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Unknown email or wrong password.')
    expect(alert.textContent).not.toContain('ana@quillmere.example')
  })

  it('does not invite another attempt while the server is refusing them', async () => {
    const retryAt = new Date(Date.now() + 30_000).toUTCString()
    stubFetch(
      Response.json(
        { code: 'login_rate_limited', detail: 'Too many attempts.' },
        { status: 429, headers: { 'retry-after': retryAt } },
      ),
    )
    renderForm()

    await userEvent.type(screen.getByLabelText('Email'), 'ana@quillmere.example')
    await userEvent.type(screen.getByLabelText('Password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent('Too many requests')
    expect(alert.querySelector('button')).toBeNull()

    const submit = screen.getByRole('button', { name: /try again in/i })
    expect(submit).toBeDisabled()
    expect(submit).toHaveTextContent(/try again in \d+ s/i)
  })

  it('leaves for the working screen once the session exists', async () => {
    stubFetch(Response.json({ user: { display_name: 'Ana' } }, { status: 200 }))
    renderForm()

    await userEvent.type(screen.getByLabelText('Email'), 'ana@quillmere.example')
    await userEvent.type(screen.getByLabelText('Password'), 'demo-analyst')
    await userEvent.click(screen.getByRole('button', { name: 'Sign in' }))

    await waitFor(() => expect(replace).toHaveBeenCalledWith('/search'))
  })
})
