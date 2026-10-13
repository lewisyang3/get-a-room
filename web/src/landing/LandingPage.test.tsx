import { render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it } from 'vitest'
import { expectNoAxeViolations } from '../test/axe'
import LandingPage from './LandingPage'

// The note's sentence is split by the "class schedule" link, so tests match
// the whole paragraph's text rather than a single text node.
function note() {
  const paragraph = screen
    .getByRole('link', { name: 'class schedule' })
    .closest('p')
  if (!paragraph)
    throw new Error('The class schedule link is not in a paragraph')
  return paragraph
}

describe('LandingPage', () => {
  beforeEach(() => {
    render(<LandingPage />)
  })

  describe('acceptance criteria (GAR-033)', () => {
    it('explains that availability comes from the class schedule', () => {
      expect(note()).toHaveTextContent(/based on the class schedule/i)
    })

    it('states that live occupancy is not supported', () => {
      expect(note()).toHaveTextContent(/not who's actually in the room/)
    })

    it('does not promise that a room is open or accessible', () => {
      expect(note()).toHaveTextContent(/rooms may be locked/i)
    })

    it('states that reservations are not supported', () => {
      expect(note()).toHaveTextContent(/can't be reserved/)
    })
  })

  describe('structure', () => {
    it('has the headline as its only heading', () => {
      expect(screen.getAllByRole('heading')).toEqual([
        screen.getByRole('heading', {
          level: 1,
          name: 'Find an empty classroom to study in.',
        }),
      ])
    })

    it('has banner and main landmarks', () => {
      expect(screen.getByRole('banner')).toBeInTheDocument()
      expect(screen.getByRole('main')).toBeInTheDocument()
    })

    it('passes axe (GAR-038)', async () => {
      await expectNoAxeViolations()
    })

    it('links to the source class schedule', () => {
      expect(
        screen.getByRole('link', { name: 'class schedule' }),
      ).toHaveAttribute('href', 'https://classes.berkeley.edu')
    })
  })
})
