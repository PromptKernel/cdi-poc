import { expect, test } from '@playwright/test'

// The API is started with a bearer token: the page must ask for it, refuse a wrong one, and load once the right one is typed.
test('live API with auth: token prompt, wrong token rejected, right token loads, token not persisted beyond the tab', async ({ page }) => {
  const consoleErrors: string[] = []
  page.on('console', (m) => { if (m.type() === 'error' && !/401/.test(m.text())) consoleErrors.push(m.text()) })
  await page.goto('/')
  const form = page.getByLabel('API token')
  await expect(form).toBeVisible()
  await expect(page.getByText('The API needs a bearer token')).toBeVisible()
  await expect(page.locator('.meta')).toHaveCount(0)

  await form.fill('wrong-token')
  await page.getByRole('button', { name: 'Use token' }).click()
  await expect(page.getByLabel('API token')).toBeVisible()               // still asking
  await expect(page.locator('.meta')).toHaveCount(0)

  await page.getByLabel('API token').fill('e2e-token-not-a-secret')
  await page.getByRole('button', { name: 'Use token' }).click()
  await expect(page.locator('.meta')).toContainText('nodes')
  await expect(page.getByTestId('data-source')).toContainText('live API (http://127.0.0.1:8766)')
  await expect(page.getByLabel('API token')).toHaveCount(0)

  // the token lives in sessionStorage only
  expect(await page.evaluate(() => sessionStorage.getItem('cdi.apiToken'))).toBe('e2e-token-not-a-secret')
  expect(await page.evaluate(() => JSON.stringify(localStorage))).not.toContain('e2e-token')
  expect(consoleErrors).toEqual([])
})
