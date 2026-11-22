/**
 * The Content-Security-Policy the API sends must not block anything the app uses: the pdf.js
 * worker, the bill image, narrated audio, Radix popovers. A blocked resource can fail silently,
 * so this listens for violation reports on every main screen.
 */
import { expect, type Page, test } from '@playwright/test';

import { loadDemo, signIn } from './support';

async function collectViolations(page: Page): Promise<string[]> {
  const violations: string[] = [];
  await page.exposeFunction('reportCsp', (v: string) => violations.push(v));
  await page.addInitScript(() => {
    document.addEventListener('securitypolicyviolation', (e) => {
      (window as unknown as { reportCsp: (v: string) => void }).reportCsp(
        `${e.violatedDirective} ${e.blockedURI}`,
      );
    });
  });
  page.on('console', (message) => {
    if (message.type() === 'error' && /Content Security Policy/i.test(message.text())) {
      violations.push(message.text());
    }
  });
  return violations;
}

test('no screen trips the Content-Security-Policy', async ({ page }) => {
  const violations = await collectViolations(page);
  await signIn(page);
  const ids = await loadDemo(page);

  await page.goto(`/claims/${ids.case_b ?? ''}`);
  await expect(page.getByRole('tab', { name: /Flags/ })).toBeVisible();
  await page.getByRole('tab', { name: /Bill lines/ }).click();
  await page.goto(`/claims/${ids.case_a ?? ''}`); // photographed bill (image)
  await expect(page.getByRole('img', { name: /bill_scanned\.jpg/ })).toBeVisible();
  await page.goto(`/claims/${ids.case_b ?? ''}/appeal`);
  await page.goto('/analytics');
  await page.goto('/settings');
  await page.keyboard.press('Control+K');
  await page.keyboard.press('Escape');

  await page.goto(`/claims/${ids.case_c ?? ''}`);
  await page.getByRole('button', { name: 'Share with family' }).click();
  await page.getByRole('button', { name: 'Create a family link' }).click();
  const link = await page.getByLabel('Family link').inputValue();
  await page.goto(new URL(link).pathname);
  await page.getByRole('button', { name: 'English' }).click();
  await page.getByRole('button', { name: /Listen/ }).click();
  await expect
    .poll(() => page.evaluate(() => document.querySelector('audio')?.currentTime ?? 0))
    .toBeGreaterThan(0.2);
  await page.goto('/check');

  expect(violations).toEqual([]);
});
