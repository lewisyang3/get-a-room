import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import App from './App'

describe('App', () => {
  it('renders the app name as the main heading', () => {
    render(<App />)

    expect(
      screen.getByRole('heading', { level: 1, name: 'Get a Room' }),
    ).toBeInTheDocument()
  })
})
