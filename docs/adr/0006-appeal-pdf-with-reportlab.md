# 0006 — Signed appeal PDFs are rendered with reportlab, not WeasyPrint

- **Status:** accepted
- **Date:** 2026-11-20

## Context

The stack table in `AGENTS.md` names WeasyPrint for the server-side appeal PDF. WeasyPrint needs
the Pango/HarfBuzz system libraries. They are in Debian images, but not on the owner's Windows
machine (no MSYS2/GTK runtime) or in a default CI runner, so the PDF could not be built or tested
where the code is developed, and the Phase 4 gate ("signed PDF opens and shows the hash") could
not be checked locally. reportlab is pure Python, is already pinned (it generates the byte-stable
demo documents in Phase 2), and has an invariant mode for reproducible output.

## Decision

- `services/appeal_pdf.py` renders the signed letter with reportlab Platypus in invariant mode:
  fictional hospital letterhead, addressee by forum, reference block, subject, facts, a
  disputed-items table (item, engine amount, insurer's reason, grounds with citation labels),
  relief, enclosures, and the "Reviewed and signed by" block. Every page's footer carries
  "Prepared with Arzi decision support; reviewed and signed by <name>", the content SHA-256 and
  "Page n of m" (a two-pass build counts the pages).
- IBM Plex Sans (regular, semibold) and IBM Plex Mono are embedded from `arzi/assets/fonts`
  (SIL Open Font License, `OFL.txt` alongside). They carry the ₹ sign; they are the planned UI
  typeface too.
- `reportlab` moves from a dev dependency to a runtime dependency; `weasyprint` is not added.

## Consequences

- The PDF builds and is tested on Windows, Linux and CI; the same signed version always gives the
  same bytes, and a test asserts it.
- reportlab does not shape complex scripts, so Devanagari and Gujarati text would not render
  correctly. Appeals are written in English (to insurers, Bima Bharosa and the Ombudsman), so
  this does not affect Phase 4. If a Hindi or Gujarati PDF is ever needed (for example a family
  summary), revisit: WeasyPrint in the container, or reportlab with HarfBuzz shaping.
- About 550 KB of font files in the repository and image.
