import AxeBuilder from '@axe-core/playwright';
import { expect, type Page } from '@playwright/test';

export const DEMO = new URL('../../demo_cases/', import.meta.url);

export async function signIn(page: Page): Promise<void> {
  await page.goto('/sign-in');
  await page.getByRole('button', { name: /Continue to the demo workspace/ }).click();
  await expect(page).toHaveURL(/\/worklist$/);
}

/** Loads cases A, B and C through the API and waits until their audits have finished. */
export async function loadDemo(page: Page): Promise<Record<string, string>> {
  const response = await page.request.post('/api/v1/demo/cases');
  expect(response.status()).toBe(202);
  const loaded = (await response.json()) as { case: string; claim_id: string }[];
  const ids = Object.fromEntries(loaded.map((c) => [c.case, c.claim_id]));
  await expect
    .poll(async () => {
      const claims = await Promise.all(
        Object.values(ids).map(
          async (id) =>
            ((await (await page.request.get(`/api/v1/claims/${id}`)).json()) as { status: string })
              .status,
        ),
      );
      return claims.every((s) => s === 'audited');
    })
    .toBe(true);
  return ids;
}

/** Zero serious or critical accessibility violations on the current screen. */
export async function expectAccessible(page: Page): Promise<void> {
  const { violations } = await new AxeBuilder({ page }).analyze();
  const blocking = violations
    .filter((v) => v.impact === 'serious' || v.impact === 'critical')
    .map((v) => `${v.id}: ${v.nodes.map((n) => n.target.join(' ')).join(', ')}`);
  expect(blocking).toEqual([]);
}
