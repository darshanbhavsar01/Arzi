# 0007 — One Cloud Run container serves the API and the built single-page app

- **Status:** accepted
- **Date:** 2026-11-20

## Context

The desk app is a Vite + React SPA; the API is FastAPI. Hosting them separately (Firebase Hosting
or a CDN for the SPA, Cloud Run for the API) means two deploys, CORS, two origins for cookies and
a second thing to keep in step with the API contract. The event build has a ₹500 budget, one
person, and a live link that must simply work.

## Decision

- The Docker image builds the SPA in a Node stage and copies `dist/` into the Python runtime;
  FastAPI mounts it at `/` (`ARZI_STATIC_DIR`) after every API and health route.
- `SpaFiles` answers client routes (`/claims/ARZ-…/appeal`, no file extension, outside `api/` and
  `assets/`) with `index.html`, so reloads and shared links open the right screen; missing files
  and unknown API paths stay RFC 7807 404s.
- Hashed assets under `/assets/` are `Cache-Control: public, max-age=31536000, immutable`;
  `index.html` is `no-cache`, so a deploy is picked up on the next navigation.
- Vendor code is split into long-lived chunks (react, data, radix) and every screen is a lazily
  loaded route; pdf.js loads only when a document is shown.
- The image also ships the synthetic demo documents and their recorded model responses
  (`ARZI_REPLAY_DIR=/app/demo_cases`) for "Load demo cases" and replay mode.

## Consequences

- One deploy, one origin, no CORS; the SPA always talks to the API version it was built with.
- Static files are served by Python rather than a CDN. For an internal desk tool on scale-to-zero
  Cloud Run this is fast enough (Lighthouse desktop 93–100 on worklist, workspace and appeal) and
  can move behind Cloud CDN later without code changes.
