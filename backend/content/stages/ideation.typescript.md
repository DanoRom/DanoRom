## For TypeScript/Next.js projects

- **Run `npx create-next-app@latest` first**, even for a throwaway spike —
  it wires up TypeScript, ESLint, and the App Router correctly in one step
  instead of assembling them by hand later.
- **Define your core types before your components.** A `types.ts` with your
  3-5 entities forces the same clarity a data-model sketch does for a backend
  project.
- **Default to the App Router** (`app/`) unless you have a specific reason
  not to — it's what current Next.js documentation and examples assume.
- **Commit `package-lock.json` from the very first commit**, not later —
  reproducibility starts at idea stage, not scaffolding.
- **Share the idea via a free Vercel Preview Deployment** before investing
  further — get one user's reaction to a real URL, not a screenshot.
