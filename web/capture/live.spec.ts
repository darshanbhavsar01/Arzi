/** Screenshots of every desk tab, the appeal flow, the family page and the free check. */
import { expect, type Page, test } from '@playwright/test';

import { loadDemo, signIn } from '../e2e/support';

const OUT = '../docs/screens/live';
const PHONE = { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true };

async function shot(page: Page, name: string, fullPage = true): Promise<void> {
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(600);
  await page.screenshot({ path: `${OUT}/${name}.png`, fullPage });
}

async function tab(page: Page, name: RegExp): Promise<void> {
  await page.getByRole('tab', { name }).click();
}

test('capture the live link', async ({ page, browser }) => {
  await page.goto('/sign-in');
  await shot(page, '01-sign-in');
  await signIn(page);
  const ids = await loadDemo(page);
  await page.goto('/worklist');
  await shot(page, '02-worklist');

  await page.goto('/audits/new');
  await shot(page, '03-new-audit');

  for (const [key, label] of [
    ['case_a', 'a-pre-submission'],
    ['case_b', 'b-deduction'],
    ['case_c', 'c-rejection'],
  ] as const) {
    await page.goto(`/claims/${ids[key] ?? ''}`);
    await expect(page.getByRole('tab', { name: /Flags/ })).toBeVisible();
    await shot(page, `04-${label}-flags`);
    await tab(page, /Bill lines/);
    await shot(page, `04-${label}-bill-lines`);
    await tab(page, /Policy terms/);
    await shot(page, `04-${label}-policy`);
    await tab(page, /Activity/);
    await shot(page, `04-${label}-activity`);
  }

  // Appeal for case B: forum checklist, draft, acknowledge Verify refs, submit, sign.
  await page.goto(`/claims/${ids.case_b ?? ''}/appeal`);
  await shot(page, '05-appeal-forum-checklist');
  await page.getByRole('button', { name: /Draft appeal for Insurer GRO/ }).click();
  await expect(page.getByText('Draft — not reviewed')).toBeVisible({ timeout: 60_000 });
  await shot(page, '06-appeal-editor');
  await page.getByLabel(/I have checked these against the primary source/).click();
  await page.getByRole('button', { name: 'Submit for review' }).click();
  await page.getByRole('button', { name: 'Review and sign' }).click();
  await page.getByLabel('Reviewer’s full name').fill('Riya Mehta');
  await page.getByLabel('Role').fill('TPA desk manager');
  await page.getByLabel(/I have read this appeal/).click();
  await shot(page, '07-sign-dialog', false);
  await page.getByRole('button', { name: 'Sign appeal' }).click();
  await expect(page.getByText(/Content SHA-256/)).toBeVisible();
  await shot(page, '08-appeal-signed', false);
  await page.keyboard.press('Escape');

  await page.goto('/appeals');
  await shot(page, '09-appeals');
  await page.goto('/analytics');
  await shot(page, '10-analytics');
  await page.goto('/settings');
  for (const [i, name] of (['Hospital', 'Team', 'Privacy', 'System'] as const).entries()) {
    await tab(page, new RegExp(name, 'i'));
    await shot(page, `11-settings-${String(i + 1)}-${name.toLowerCase()}`);
  }
  await page.goto('/worklist');
  await page.keyboard.press('Control+K');
  await shot(page, '12-command-palette', false);
  await page.keyboard.press('Escape');

  // Family page on a phone, in all three languages.
  await page.goto(`/claims/${ids.case_b ?? ''}`);
  await page.getByRole('button', { name: 'Share with family' }).click();
  await page.getByRole('button', { name: 'Create a family link' }).click();
  const link = await page.getByLabel('Family link').inputValue();
  await shot(page, '13-share-dialog', false);
  const phone = await browser.newContext({ ...PHONE, locale: 'gu-IN' });
  const family = await phone.newPage();
  await family.goto(new URL(link).pathname);
  await expect(family.locator('article[lang="gu"]')).toBeVisible({ timeout: 60_000 });
  await shot(family, '14-family-gujarati');
  await family.getByRole('button', { name: 'हिन्दी' }).click();
  await expect(family.locator('article[lang="hi"]')).toBeVisible();
  await shot(family, '15-family-hindi');
  await family.getByRole('button', { name: 'English' }).click();
  await expect(family.locator('article[lang="en"]')).toBeVisible();
  await shot(family, '16-family-english');
  await family.goto('/check');
  await shot(family, '17-free-check-phone');
  await phone.close();

  await page.goto('/check');
  await shot(page, '18-free-check');
});
