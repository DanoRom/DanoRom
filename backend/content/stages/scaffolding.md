# Stage: Scaffolding

The skeleton exists — folders, configs, maybe a hello-world — but the foundation
isn't stable yet.

## What this stage is about
Making the project reproducible and structured so feature work doesn't fight the
tooling later.

## Key activities
- **Lock your dependencies.** Commit a lockfile (`package-lock.json`, `poetry.lock`)
  so every machine builds the same thing.
- **Separate concerns early.** Source, tests, and configuration in distinct folders.
- **Document environment variables.** A `.env.example` beats tribal knowledge.
- **One-command startup.** `npm run dev` or `make dev` should bring everything up.

## You're ready for the next stage when
- A new developer can clone, install, and run in under ten minutes.
- One vertical slice (UI → API → database) works end to end.
