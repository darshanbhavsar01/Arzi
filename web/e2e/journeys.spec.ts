/**
 * The three demo journeys, end to end in the browser (replay mode):
 *   A — upload a pre-submission claim, watch the audit, read the flags and their fix.
 *   B — appeal a deduction: draft, acknowledge Verify refs, submit, sign, export the PDF.
 *   C — appeal a rejection: the 36-month PED cap, and the Ombudsman checklist.
 */
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

import { DEMO, expectAccessible, loadDemo, signIn } from './support';

test('sign-in explains the product and is accessible', async ({ page }) => {
  await page.goto('/worklist');
  await expect(page).toHaveURL(/\/sign-in$/);
  await expect(page.getByRole('heading', { level: 1 })).toHaveText(
    'Your claim, defended before and after the insurer says no.',
  );
  await expectAccessible(page);
});

test('journey A: upload → streamed audit → flags → fix', async ({ page }) => {
  await signIn(page);
  await page.getByRole('link', { name: 'New audit' }).first().click();
  await page.getByText('Pre-submission audit').first().click();
  await page.getByRole('button', { name: 'Continue' }).click();
  const files = [
    'policy_schedule.pdf',
    'policy_wording_excerpt.pdf',
    'bill_scanned.jpg',
    'discharge_summary.pdf',
    'investigation_reports.pdf',
    'implant_invoice.pdf',
  ].map((name) => fileURLToPath(new URL(`case_a/${name}`, DEMO)));
  await page.locator('input[type=file]').setInputFiles(files);
  await expect(
    page.getByRole('list', { name: 'Documents to upload' }).getByRole('listitem'),
  ).toHaveCount(6);
  await expectAccessible(page);
  await page.getByRole('button', { name: 'Continue' }).click();

  const run = page.getByRole('button', { name: 'Run audit' });
  await expect(run).toBeDisabled(); // consent first
  await page.getByLabel(/Consent was given/).click();
  await run.click();

  await expect(page).toHaveURL(/\/claims\/ARZ-/);
  await expect(
    page.getByRole('heading', { name: /Proportionate deduction/ }).first(),
  ).toBeVisible();
  await expect(page.getByText('₹67,887.50').first()).toBeVisible();
  await expect(page.getByText('₹46,875').first()).toBeVisible(); // saved by the fixes
  await expect(page.getByRole('tab', { name: /Flags/ })).toContainText('4');
  await expect(page.getByText(/identifiers redacted/)).toBeVisible();
  await expectAccessible(page);

  // The fix, the maths and a recorded decision.
  const card = page.getByRole('article').filter({ hasText: 'Proportionate' }).first();
  await expect(
    card.getByText('Move to an eligible room, or take written upgrade consent'),
  ).toBeVisible();
  await card.getByRole('button', { name: 'Show the maths' }).click();
  await expect(card.getByText(/× ₹5,000 \/ ₹8,000/)).toBeVisible();
  await card.getByRole('button', { name: 'Accept' }).click();
  await expect(card.getByText('Accepted')).toBeVisible();

  // A bill line opens the photographed bill.
  await card.getByRole('button', { name: /Line 3/ }).click();
  await expect(page.getByRole('img', { name: /bill_scanned\.jpg/ })).toBeVisible();
});

test('journey B: deduction appeal → sign → PDF', async ({ page }) => {
  await signIn(page);
  const ids = await loadDemo(page);
  await page.goto(`/claims/${ids.case_b ?? ''}`);
  await expect(page.getByText('₹20,137.50').first()).toBeVisible();
  await page.getByRole('link', { name: 'Draft appeal' }).click();

  await expect(page.getByRole('radio', { name: /Insurance Ombudsman/ })).toBeDisabled();
  await page.getByRole('button', { name: /Draft appeal for Insurer GRO/ }).click();
  await expect(page.getByText('Draft — not reviewed')).toBeVisible();
  await expect(page.getByText('₹19,237.50').first()).toBeVisible();
  await expect(page.getByText('₹900.00').first()).toBeVisible();
  await expectAccessible(page);

  const submit = page.getByRole('button', { name: 'Submit for review' });
  await expect(submit).toBeDisabled(); // a Verify reference must be acknowledged
  await page.getByLabel(/I have checked these against the primary source/).click();
  await submit.click();
  await page.getByRole('button', { name: 'Review and sign' }).click();
  await page.getByLabel('Reviewer’s full name').fill('Riya Mehta');
  await page.getByLabel('Role').fill('TPA desk manager');
  await page.getByLabel(/I have read this appeal/).click();
  await page.getByRole('button', { name: 'Sign appeal' }).click();
  await expect(page.getByText(/Content SHA-256/)).toBeVisible();

  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', { name: 'Export signed PDF' }).click(),
  ]);
  expect(download.suggestedFilename()).toMatch(/-appeal-v1\.pdf$/);
  const path = await download.path();
  const { readFile } = await import('node:fs/promises');
  expect((await readFile(path)).subarray(0, 5).toString()).toBe('%PDF-');
});

test('journey C: rejection appeal cites the 36-month PED cap; Ombudsman opens after a reply', async ({
  page,
}) => {
  await signIn(page);
  const ids = await loadDemo(page);
  await page.goto(`/claims/${ids.case_c ?? ''}/appeal`);

  const ombudsman = page.getByRole('radio', { name: /Insurance Ombudsman/ });
  await expect(ombudsman).toBeDisabled();
  await page.getByLabel('Filed on').fill('2026-10-26');
  await page.getByLabel('Outcome').selectOption('rejected');
  await page.getByLabel('Reply received on').fill('2026-11-10');
  await expect(ombudsman).toBeEnabled();
  await expectAccessible(page);

  await page.getByRole('button', { name: /Draft appeal for Insurer GRO/ }).click();
  await expect(page.getByText('₹3,10,000.00').first()).toBeVisible();
  await expect(
    page
      .getByRole('button', { name: /Pre-existing disease: look-back and maximum waiting period/ })
      .first(),
  ).toBeVisible();
  await expectAccessible(page);
});
