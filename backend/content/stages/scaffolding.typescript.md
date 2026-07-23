## For TypeScript/Next.js projects

- **Enable `"strict": true` in `tsconfig.json`** from day one — retrofitting
  strict mode onto a growing codebase is far more painful than starting with
  it.
- **Separate `app/` (routes), `components/`, and `lib/`** so UI, page
  composition, and API/data-fetching logic don't tangle together.
- **Centralize API calls in one `lib/api.ts`** with a shared `fetch`
  wrapper — a single place to add auth headers, error handling, or a base
  URL later.
- **Add `.env.local.example`** documenting every `NEXT_PUBLIC_*` variable —
  anything without that prefix stays server-only, which matters once you
  handle secrets.
- **`npm run dev` should be the only command needed** to start the frontend;
  document any backend dependency (like this repo's FastAPI service) in the
  README.
