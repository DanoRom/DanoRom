## For TypeScript/Next.js projects

- **Add a GitHub Actions workflow** running
  `npm ci && npm run lint && npm run build` on every push (add `npm test`
  once you have a test suite).
- **Enable ESLint's `next/core-web-vitals` config** — it catches
  accessibility and performance issues that are specific to Next.js.
- **Run `npm run build` locally before every push.** It catches type errors
  and invalid Server/Client component boundaries that dev mode lets slide.
- **Read `NEXT_PUBLIC_API_URL` from the environment**, never hardcode
  `localhost` — that's what makes the same build work in every environment
  without a code change.
- **Add a `Dockerfile` using Next.js's standalone output**
  (`output: "standalone"` in `next.config.mjs`) if you plan to containerize
  the frontend.
