## For TypeScript/Next.js projects

- **Add Vitest or Jest with React Testing Library** for components, and
  Playwright for the critical end-to-end user flows.
- **Test `lib/api.ts` against a mocked `fetch`**, not just components — this
  is where response-shape bugs against the backend hide.
- **Keep server logic out of client components.** Anything marked
  `"use client"` should be presentation; data fetching belongs in server
  components or route handlers.
- **Give every component a small, explicit props interface** — TypeScript
  then catches integration bugs at compile time instead of in the browser.
- **Ship behind small PRs.** Next.js's fast refresh makes it tempting to
  build a big feature on one branch; resist it the same way you would in any
  other stack.
