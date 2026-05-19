# security.md

Advisory sweep log per CLAUDE.md §Security.

## Packages in use

| package   | version | source                                  | last advisory sweep |
| --------- | ------- | --------------------------------------- | ------------------- |
| pymupdf   | 1.26.5  | preinstalled in system Python 3.9       | 2026-05-18          |
| pydantic  | 2.9.2   | preinstalled in system Python 3.9       | 2026-05-18          |

No `pip install` was run during initial scaffolding — both packages were already present on the user's machine. Refresh sweep before adding any new dependency.

## Secrets

- No API keys are required by this project (USGS publishes MCS PDFs without auth).
- `.env*` is gitignored as a precaution.

## Network etiquette

The fetcher uses a 2s delay between requests to `pubs.usgs.gov`, sends a descriptive `User-Agent`, and caches every download under `data/raw/`. Re-runs hit local disk.
