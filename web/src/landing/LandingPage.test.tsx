import { render, screen, within } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import LandingPage from './LandingPage'

function limitations() {
  return screen.getByRole('region', { name: 'Before you go' })
}

describe('LandingPage', () => {
  beforeEach(() => {
    render(<LandingPage />)
  })

  describe('acceptance criteria (GAR-033)', () => {
    it('explains that availability comes from the class schedule', () => {
      const howItWorks = screen.getByRole('region', { name: 'How it works' })

      expect(
        within(howItWorks).getByText(/the term's scheduled classes/),
      ).toBeInTheDocument()
      expect(
        within(limitations()).getByRole('heading', {
          name: 'Scheduled, not live',
        }),
      ).toBeInTheDocument()
    })

    it('does not promise that a room is open or accessible', () => {
      const section = limitations()

      expect(
        within(section).getByRole('heading', {
          name: 'No guarantee of access',
        }),
      ).toBeInTheDocument()
      expect(
        within(section).getByText(
          /may still be locked or not open to students/,
        ),
      ).toBeInTheDocument()
    })

    it('states that live occupancy is not supported', () => {
      expect(
        within(limitations()).getByText(
          /doesn't track who is actually in a room/,
        ),
      ).toBeInTheDocument()
    })

    it('states that reservations are not supported', () => {
      const section = limitations()

      expect(
        within(section).getByRole('heading', { name: 'No reservations' }),
      ).toBeInTheDocument()
      expect(within(section).getByText(/can't be booked/)).toBeInTheDocument()
    })
  })

  describe('structure', () => {
    it('has one h1 followed by the two section headings', () => {
      expect(screen.getAllByRole('heading', { level: 1 })).toHaveLength(1)
      expect(
        screen
          .getAllByRole('heading', { level: 2 })
          .map((heading) => heading.textContent),
      ).toEqual(['How it works', 'Before you go'])
    })

    it('has banner, main and footer landmarks', () => {
      expect(screen.getByRole('banner')).toBeInTheDocument()
      expect(screen.getByRole('main')).toBeInTheDocument()
      expect(screen.getByRole('contentinfo')).toBeInTheDocument()
    })

    it('links to the source class schedule', () => {
      expect(
        screen.getByRole('link', { name: 'classes.berkeley.edu' }),
      ).toHaveAttribute('href', 'https://classes.berkeley.edu')
    })
  })
})
