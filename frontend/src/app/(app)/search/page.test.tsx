import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'

import SearchPage from './page'

describe('SearchPage', () => {
  it('renders the heading', () => {
    render(<SearchPage />)
    expect(screen.getByRole('heading', { name: 'Search' })).toBeInTheDocument()
  })
})
