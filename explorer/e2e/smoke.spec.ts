import { expect, test, type Page } from '@playwright/test'

const visible = (page: Page) => page.getByTestId('visible-nodes')

async function pick(page: Page, text: string, kind: string) {
  await page.locator('#search').fill(text)
  await page.getByRole('option', { name: new RegExp(`${text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s+${kind}`) }).first().click()
}

test('explorer smoke: search, expand, trace UI -> SQL in both directions, styles, panel, reports', async ({ page }) => {
  const external: string[] = []
  page.on('request', (r) => { const u = r.url(); if (!u.startsWith('http://127.0.0.1:4173') && !u.startsWith('data:') && !u.startsWith('blob:')) external.push(u) })
  const consoleErrors: string[] = []
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })

  await test.step('loads the built app with the synthetic-data banner', async () => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Dependency explorer' })).toBeVisible()
    await expect(page.getByRole('note').first()).toContainText('Synthetic sample data')
    await expect(page.locator('.meta')).toContainText('nodes')
  })

  await test.step('search FetchEmployeeComponent and expand its dependencies down to a SQL table', async () => {
    await pick(page, 'FetchEmployeeComponent', 'UI_COMPONENT')
    await expect(visible(page)).toContainText('FetchEmployeeComponent')
    await page.locator('#depth').fill('12')
    await expect(page.getByLabel(/Depth: 12/)).toBeVisible()
    // click the node ON THE CANVAS: selects it and expands per the chosen direction and depth
    const pos = await page.evaluate(() => { const c = (window as any).__cy; const n = c.nodes()[0]; const p = n.renderedPosition(); const r = c.container().getBoundingClientRect(); return { x: r.left + p.x, y: r.top + p.y } })
    await page.mouse.click(pos.x, pos.y)
    for (const name of ['EmployeeService.getEmployees', 'GET api/Employee/Index', 'EmployeeController.Index()', 'IEmployee.GetAllEmployees()', 'EmployeeDataAccessLayer.GetAllEmployees()', 'dbo.spGetAllEmployees', 'dbo.tblEmployee'])
      await expect(visible(page)).toContainText(name)
    await expect(page.getByText(/depth 12/)).toBeVisible()
  })

  await test.step('the three confidence styles are drawn and listed in the legend', async () => {
    const kinds = await page.evaluate(() => { const c = (window as any).__cy; return [...new Set(c.edges().map((e: any) => e.data('confidence')))].sort() })
    expect(kinds).toEqual(expect.arrayContaining(['CONFIRMED_STATIC', 'INFERRED']))
    const styles = await page.evaluate(() => { const c = (window as any).__cy; const o: Record<string, string[]> = {}
      c.edges().forEach((e: any) => { const k = e.data('confidence'); o[k] = [e.style('line-style'), e.style('line-color'), e.style('target-arrow-shape')] }); return o })
    expect(styles.CONFIRMED_STATIC[0]).toBe('solid'); expect(styles.INFERRED[0]).toBe('dashed')
    expect(styles.CONFIRMED_STATIC[1]).not.toBe(styles.INFERRED[1])
    expect(styles.CONFIRMED_STATIC[2]).not.toBe(styles.INFERRED[2])
    const legend = page.getByLabel('Legend')
    for (const t of ['CONFIRMED_STATIC', 'INFERRED', 'UNRESOLVED', 'solid', 'dashed', 'dotted', 'Synthetic']) await expect(legend).toContainText(t)
  })

  await test.step('side panel: an inferred edge shows its reason, evidence, commit and an exact-file GitHub link', async () => {
    await visible(page).getByRole('button', { name: 'ASPCoreWithAngular.Interfaces.IEmployee.GetAllEmployees()' }).click()
    await expect(page.getByTestId('node-panel')).toContainText('INTERFACE_METHOD')
    await page.getByTestId('node-panel').getByRole('button', { name: /DISPATCHES_TO/ }).click()
    const ep = page.getByTestId('edge-panel')
    await expect(ep).toContainText('INFERRED')
    await expect(ep).toContainText('runtime DI decision')
    await expect(ep).toContainText('roslyn:interface-implementation')
    const href = await ep.getByRole('link', { name: /view on GitHub/ }).getAttribute('href')
    expect(href).toMatch(/\/blob\/[0-9a-f]{40}\/samples\/api\/DataAccess\/EmployeeDataAccessLayer\.cs#L22$/)
  })

  await test.step('reverse direction: from the SQL table, downstream consumers reach the screen', async () => {
    await page.getByRole('button', { name: 'Clear' }).click()
    await pick(page, 'dbo.tblEmployee', 'SQL_TABLE')
    await page.getByLabel(/Downstream: consumers/).check()
    await page.locator('#depth').fill('12')
    await page.getByRole('button', { name: 'Expand selected' }).click()
    await expect(visible(page)).toContainText('FetchEmployeeComponent')
    await expect(visible(page)).toContainText('dbo.spGetAllEmployees')
  })

  await test.step('unresolved / not-found nodes are distinct and explain why', async () => {
    await page.getByRole('button', { name: 'Clear' }).click()
    await pick(page, 'DepartmentReportService.getHeadcount', 'UI_SERVICE_METHOD')
    await page.getByLabel(/Upstream: dependencies/).check()
    await page.getByRole('button', { name: 'Expand selected' }).click()
    await visible(page).getByRole('button', { name: /✕|unresolved|<unresolved URL>/i }).first().click()
    const np = page.getByTestId('node-panel')
    await expect(np).toContainText('unresolved / not found')
    await expect(np).toContainText('runtime configuration')
    const shape = await page.evaluate(() => { const c = (window as any).__cy; const n = c.nodes('[kind = "UNRESOLVED"]')[0]; return [n.style('shape'), n.style('border-style')] })
    expect(shape).toEqual(['octagon', 'dashed'])
  })

  await test.step('filters: confidence and repo filters change what is searchable/expandable', async () => {
    await page.getByRole('button', { name: 'Clear' }).click()
    await page.getByLabel('INFERRED', { exact: true }).uncheck()
    await pick(page, 'FetchEmployeeComponent', 'UI_COMPONENT')
    await page.getByLabel(/Upstream: dependencies/).check()
    await page.locator('#depth').fill('12')
    await page.getByRole('button', { name: 'Expand selected' }).click()
    await expect(visible(page)).toContainText('EmployeeController.Index()')
    await expect(visible(page)).not.toContainText('dbo.tblEmployee')      // the path is cut at the INFERRED dispatch hop
    await page.getByLabel('INFERRED', { exact: true }).check()
  })

  await test.step('Reports page lists and renders impact reports; PR comment preview is labelled simulated', async () => {
    await page.getByRole('link', { name: 'Reports' }).click()
    await expect(page.getByRole('heading', { name: /Impact reports \(\d+\)/ })).toBeVisible()
    await page.getByRole('button', { name: /pr-e-delete-proc/ }).click()
    await expect(page.getByRole('heading', { name: /Impact report: pr-e-delete-proc/ })).toBeVisible()
    await expect(page.locator('.md table').first()).toBeVisible()
    await page.getByRole('link', { name: 'PR comment preview' }).click()
    await expect(page.locator('.sim')).toContainText('Simulated')
    await expect(page.locator('.sim')).toContainText('not tested against a real service')
    await expect(page.locator('.json')).toContainText('"simulated": true')
    await expect(page.locator('.marker')).toContainText('cdi-poc:impact-report:v1')
  })

  expect(external, 'no request may leave localhost (no CDNs, no telemetry)').toEqual([])
  expect(consoleErrors, 'no console errors').toEqual([])
})
