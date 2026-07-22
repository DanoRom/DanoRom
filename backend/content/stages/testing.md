# Stage: Testing

Tests exist — now make quality automatic instead of heroic.

## What this stage is about
Building the machinery that keeps the project green without anyone remembering
to check.

## Key activities
- **Add continuous integration.** Run the suite on every push — GitHub Actions has
  a generous free tier.
- **Lint and format automatically.** Arguments about style are a tax; automate them away.
- **Containerize.** A Dockerfile makes "works on my machine" mean every machine.
- **Externalize configuration.** All secrets and URLs come from environment variables.

## You're ready for the next stage when
- A red build blocks a merge, and a green build means deployable.
- The app runs identically in a container and on a laptop.
