# Deployment

The package publishes to PyPI from main through the shared pipelines workflow in `.github/workflows/pipeline.yml`. The documentation publishes to GitHub Pages through `.github/workflows/pages.yml`.

The `Dockerfile` builds a two-stage image on `python:3.13-slim`. Its entry point is `agent-terminal-ui`.
