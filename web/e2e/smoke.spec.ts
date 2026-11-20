import AxeBuilder from '@axe-core/playwright';
import { expect, test } from '@playwright/test';

test('placeholder page renders with no serious accessibility violations', async ({ page }) => {
  await page.goto('/');

  await expect(page.getByRole('heading', { level: 1, name: 'Arzi' })).toBeVisible();

  const { violations } = await new AxeBuilder({ page }).analyze();
  const blocking = violations.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  expect(blocking).toEqual([]);
});
