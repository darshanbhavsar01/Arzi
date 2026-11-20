/**
 * The family experience on a phone (replay mode): the desk shares case C, the family opens the
 * link, listens in Gujarati and switches to Hindi and English; and the free public check runs
 * from upload to a signed appeal PDF.
 */
import { fileURLToPath } from 'node:url';

import { expect, test } from '@playwright/test';

import { DEMO, expectAccessible, loadDemo, signIn } from './support';

const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true };

test('desk shares case C; the family listens in Gujarati and switches language', async ({
  page,
  browser,
}) => {
  await signIn(page);
  const ids = await loadDemo(page);
  await page.goto(`/claims/${ids.case_c ?? ''}`);
  await page.getByRole('button', { name: 'Share with family' }).click();
  await page.getByRole('button', { name: 'Create a family link' }).click();
  const link = await page.getByLabel('Family link').inputValue();
  expect(link).toMatch(/\/f\/[\w-]{40,}$/);

  const phone = await browser.newContext({ ...PHONE, locale: 'gu-IN' });
  const family = await phone.newPage();
  await family.goto(new URL(link).pathname);

  const article = family.locator('article[lang="gu"]');
  await expect(article.getByRole('heading', { level: 1 })).toContainText(/[઀-૿]/);
  await expect(family.getByText('₹3,10,000').first()).toBeVisible();
  await expectAccessible(family);

  await family.getByRole('button', { name: 'સાંભળો' }).click();
  await expect
    .poll(() => family.evaluate(() => document.querySelector('audio')?.currentTime ?? 0), {
      timeout: 15_000,
    })
    .toBeGreaterThan(0.3);
  await family.getByRole('button', { name: 'રોકો' }).click();

  await family.getByRole('button', { name: 'हिन्दी' }).click();
  await expect(
    family.locator('article[lang="hi"]').getByRole('heading', { level: 1 }),
  ).toContainText(/[ऀ-ॿ]/);
  await family.getByRole('button', { name: 'English' }).click();
  await expect(
    family.locator('article[lang="en"]').getByRole('heading', { level: 1 }),
  ).toBeVisible();
  await expect(
    family.getByText('A qualified person at the hospital checks and signs every appeal.'),
  ).toBeVisible();
  // Nothing scrolls sideways on a 390 px screen.
  expect(await family.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
    390,
  );
  await phone.close();
});

test('free check: upload → audit → explanation → the family signs the appeal', async ({
  browser,
}) => {
  const phone = await browser.newContext({ ...PHONE, locale: 'en-IN', acceptDownloads: true });
  const page = await phone.newPage();
  await page.goto('/check');
  await page.getByRole('button', { name: 'English' }).click();
  await expectAccessible(page);

  const file = (name: string) => fileURLToPath(new URL(`case_c/${name}`, DEMO));
  await page.getByText('Rejected the claim').click();
  await page.locator('#check-letter').setInputFiles(file('insurer_rejection_letter.pdf'));
  await page
    .locator('#check-policy')
    .setInputFiles([file('policy_schedule.pdf'), file('policy_wording_excerpt.pdf')]);
  await page.locator('#check-bill').setInputFiles(file('itemised_bill.pdf'));
  await page.locator('#check-discharge').setInputFiles(file('discharge_summary.pdf'));
  const submit = page.getByRole('button', { name: 'Check my claim' });
  await expect(submit).toBeDisabled();
  await page.getByLabel(/I agree that Arzi may read these documents/).click();
  await submit.click();

  await expect(page).toHaveURL(/\/f\//);
  await expect(page.locator('article[lang="en"]').getByRole('heading', { level: 1 })).toBeVisible({
    timeout: 45_000,
  });
  await page.getByRole('button', { name: 'Draft my appeal letter' }).click();
  await expect(page.getByText('₹3,10,000').first()).toBeVisible();
  await page.getByLabel('Your full name').fill('Mahendra Patel');
  await page.getByLabel(/I have read this letter/).click();
  await page.getByRole('button', { name: 'Sign the letter' }).click();
  await expect(page.getByText('Signed by Mahendra Patel')).toBeVisible();
  const [download] = await Promise.all([
    page.waitForEvent('download'),
    page.getByRole('link', { name: /Download the signed letter/ }).click(),
  ]);
  expect(download.suggestedFilename()).toBe('appeal-v1.pdf');
  await expectAccessible(page);
  await phone.close();
});

test('an unknown family link explains itself instead of erroring', async ({ browser }) => {
  const phone = await browser.newContext({ ...PHONE, locale: 'en-IN' });
  const page = await phone.newPage();
  await page.goto('/f/this-link-does-not-exist');
  await page.getByRole('button', { name: 'English' }).click();
  await expect(page.getByRole('heading', { name: 'This link has expired' })).toBeVisible();
  await phone.close();
});
