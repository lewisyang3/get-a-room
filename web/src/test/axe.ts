import axe from 'axe-core'

type Options = {
  /** Whether to require all content to be inside landmarks. Off for
   * components rendered on their own, without the page around them. */
  region?: boolean
}

/** Runs axe over `container` and fails with each violation's rule, help text
 * and the elements it found. jsdom has no layout, so color contrast isn't
 * checked here; the color tokens in index.css are chosen to meet WCAG AA. */
export async function expectNoAxeViolations(
  container: Element = document.body,
  { region = true }: Options = {},
): Promise<void> {
  const { violations } = await axe.run(container, {
    rules: {
      'color-contrast': { enabled: false },
      region: { enabled: region },
    },
  })
  if (violations.length === 0) return
  const report = violations
    .map((violation) => {
      const targets = violation.nodes
        .map((node) => `    ${node.target.join(' ')}`)
        .join('\n')
      return `${violation.id}: ${violation.help}\n${targets}`
    })
    .join('\n')
  throw new Error(`Accessibility violations:\n${report}`)
}
