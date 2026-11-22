# Arzi: every screen

Captured from the deployed app (Cloud Run, Mumbai) on 22 November 2026, before the event
deployment was retired. All data is synthetic; the hospital and insurer are fictional.

Regenerate against any deployment: `cd web && LIVE_URL=<url> npx playwright test -c capture/live.config.ts`.

### Sign-in: one click into the demo workspace

![Sign-in: one click into the demo workspace](01-sign-in.png)

### Worklist: every claim, status, ₹ at risk and audit time

![Worklist: every claim, status, ₹ at risk and audit time](02-worklist.png)

### New audit wizard: decision stage, documents, consent

![New audit wizard: decision stage, documents, consent](03-new-audit.png)

### Case A (before filing): flags with citations, fix and savings, beside the photographed bill

![Case A (before filing): flags with citations, fix and savings, beside the photographed bill](04-a-pre-submission-flags.png)

### Case A: extracted bill lines with categories and confidence

![Case A: extracted bill lines with categories and confidence](04-a-pre-submission-bill-lines.png)

### Case A: policy terms read from the wording

![Case A: policy terms read from the wording](04-a-pre-submission-policy.png)

### Case A: append-only activity log

![Case A: append-only activity log](04-a-pre-submission-activity.png)

### Case B (insurer deduction): what the rules dispute

![Case B (insurer deduction): what the rules dispute](04-b-deduction-flags.png)

### Case B: bill lines

![Case B: bill lines](04-b-deduction-bill-lines.png)

### Case B: policy terms

![Case B: policy terms](04-b-deduction-policy.png)

### Case B: activity

![Case B: activity](04-b-deduction-activity.png)

### Case C (rejection): the 36-month pre-existing disease rule

![Case C (rejection): the 36-month pre-existing disease rule](04-c-rejection-flags.png)

### Case C: bill lines

![Case C: bill lines](04-c-rejection-bill-lines.png)

### Case C: policy terms

![Case C: policy terms](04-c-rejection-policy.png)

### Case C: activity

![Case C: activity](04-c-rejection-activity.png)

### Appeal: forum checklist (insurer GRO, Bima Bharosa, Ombudsman eligibility)

![Appeal: forum checklist (insurer GRO, Bima Bharosa, Ombudsman eligibility)](05-appeal-forum-checklist.png)

### Appeal editor: clause-cited draft, amounts filled from the rules engine

![Appeal editor: clause-cited draft, amounts filled from the rules engine](06-appeal-editor.png)

### Human sign-off: named reviewer, role and declaration

![Human sign-off: named reviewer, role and declaration](07-sign-dialog.png)

### Signed and sealed with a SHA-256 of the exact content

![Signed and sealed with a SHA-256 of the exact content](08-appeal-signed.png)

### Appeals across the desk

![Appeals across the desk](09-appeals.png)

### Analytics: ₹ at risk by insurer, stage and week; recovery funnel

![Analytics: ₹ at risk by insurer, stage and week; recovery funnel](10-analytics.png)

### Settings: hospital room tariff

![Settings: hospital room tariff](11-settings-1-hospital.png)

### Settings: team and roles

![Settings: team and roles](11-settings-2-team.png)

### Settings: data and privacy

![Settings: data and privacy](11-settings-3-privacy.png)

### Settings: AI mode, models, prompt versions, budget

![Settings: AI mode, models, prompt versions, budget](11-settings-4-system.png)

### Command palette (Ctrl/⌘ K)

![Command palette (Ctrl/⌘ K)](12-command-palette.png)

### Share with the family: a private, expiring link

![Share with the family: a private, expiring link](13-share-dialog.png)

### Family page on a phone, in Gujarati, with narration

![Family page on a phone, in Gujarati, with narration](14-family-gujarati.png)

### Family page in Hindi

![Family page in Hindi](15-family-hindi.png)

### Family page in English

![Family page in English](16-family-english.png)

### Free rejection check on a phone

![Free rejection check on a phone](17-free-check-phone.png)

### Free rejection check on a laptop

![Free rejection check on a laptop](18-free-check.png)
