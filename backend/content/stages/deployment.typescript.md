## For TypeScript/Next.js projects

- **Deploy on Vercel's free Hobby tier** — import the repo, set the root
  directory to `frontend/`, and Next.js is auto-detected.
- **Set `NEXT_PUBLIC_API_URL`** in the Vercel project's environment
  variables to point at your deployed backend — the `NEXT_PUBLIC_` prefix is
  required for the value to reach the browser.
- **Every push to `main` deploys to production; every PR gets a free preview
  URL** — use previews to sanity-check before merging.
- **Search `next.config.mjs` and `lib/api.ts` for hardcoded `localhost`
  URLs** before deploying — they will silently break in production.
- **Add a custom domain later, at no extra cost**, once the default
  `*.vercel.app` URL has proven the deploy works end to end.
