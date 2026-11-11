import { expect, test, type Page } from '@playwright/test'
import { readFileSync } from 'node:fs'

const visible = (page: Page) => page.getByTestId('visible-nodes')

async function pick(page: Page, text: string, kind: string) {
  await page.locator('#search').fill(text)
  await page.getByRole('option', { name: new RegExp(`${text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s+${kind}`) }).first().click()
}

test('explorer smoke: search, expand, trace UI -> SQL in both directions, styles, panel, reports', async ({ page }) => {
  const external: string[] = []
  const mode = test.info().project.name                       // 'snapshot' or 'live'
  const live = mode === 'live'
  const allowed = [test.info().project.use.baseURL!, 'http://127.0.0.1:8765', 'data:', 'blob:']        // localhost app and, in live mode, the localhost API
  const urls: string[] = []
  page.on('request', (r) => { const u = r.url(); urls.push(u); if (!allowed.some((a) => u.startsWith(a))) external.push(u) })
  const consoleErrors: string[] = []
  page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()) })

  await test.step('loads the built app with the synthetic-data banner', async () => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Dependency explorer' })).toBeVisible()
    await expect(page.getByTestId('notice')).toContainText('Structure only')   // the notice text is part of the data (meta.notice)
    await expect(page.locator('.meta')).toContainText('nodes')
  })

  await test.step('shows where the data comes from: live API or snapshot', async () => {
    const ind = page.getByTestId('data-source')
    await expect(ind).toHaveAttribute('data-kind', live ? 'live' : 'snapshot')
    await expect(ind).toContainText(live ? 'live API (http://127.0.0.1:8765)' : 'snapshot')
    if (live) await expect(ind).not.toContainText('snapshot')
  })

  await test.step('Analyze panel: baseline commit of every repo, load time, schema version', async () => {
    await page.getByRole('link', { name: 'Analyze' }).click()
    const panel = page.getByTestId('analyze-panel')
    await expect(panel).toBeVisible()
    await expect(page.getByTestId('analyze-source')).toContainText(live ? 'live API' : 'snapshot')
    const baseline = JSON.parse(readFileSync(new URL('./fixtures/live/baseline.json', import.meta.url), 'utf8')).freshness   // the commits the baseline was built from
    for (const [repo, sha] of Object.entries(baseline.commits as Record<string, string>))
      await expect(page.getByTestId(`commit-${repo}`)).toHaveText(sha)
    // the snapshot fixture predates schema versions: the panel must say so rather than invent a value
    await expect(page.getByTestId('analyze-schema')).toHaveText(live ? '1' : 'not recorded')
    await expect(page.getByTestId('analyze-loaded')).toContainText(live ? '2026-01-01T00:00:00+00:00' : '')
    await page.getByRole('link', { name: 'Graph' }).click()
  })

  await test.step('search FetchItemComponent and expand its dependencies down to a SQL table', async () => {
    await pick(page, 'FetchItemComponent', 'UI_COMPONENT')
    await expect(visible(page)).toContainText('FetchItemComponent')
    await page.locator('#depth').fill('12')
    await expect(page.getByLabel(/Depth: 12/)).toBeVisible()
    // click the node ON THE CANVAS: selects it and expands per the chosen direction and depth
    const pos = await page.evaluate(() => { const c = (window as any).__cy; const n = c.nodes()[0]; const p = n.renderedPosition(); const r = c.container().getBoundingClientRect(); return { x: r.left + p.x, y: r.top + p.y } })
    await page.mouse.click(pos.x, pos.y)
    for (const name of ['ItemService.getItems', 'GET api/Item/Index', 'ItemController.Index()', 'IItem.GetAllItems()', 'ItemDataAccessLayer.GetAllItems()', 'dbo.spGetAllItems', 'dbo.tblItem'])
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
    await visible(page).getByRole('button', { name: 'ShopApp.Interfaces.IItem.GetAllItems()' }).click()
    await expect(page.getByTestId('node-panel')).toContainText('INTERFACE_METHOD')
    await page.getByTestId('node-panel').getByRole('button', { name: /DISPATCHES_TO/ }).click()
    const ep = page.getByTestId('edge-panel')
    await expect(ep).toContainText('INFERRED')
    await expect(ep).toContainText('runtime DI decision')
    await expect(ep).toContainText('roslyn:interface-implementation')
    const href = await ep.getByRole('link', { name: /view on GitHub/ }).getAttribute('href')
    // the folder comes from the data source's repo list: apps/api in the snapshot, api in the live config
    expect(href).toMatch(/\/blob\/[0-9a-f]{40}\/(apps\/)?api\/DataAccess\/ItemDataAccessLayer\.cs#L22$/)
  })

  await test.step('reverse direction: from the SQL table, downstream consumers reach the screen', async () => {
    await page.getByRole('button', { name: 'Clear' }).click()
    await pick(page, 'dbo.tblItem', 'SQL_TABLE')
    await page.getByLabel(/Downstream: affected by this \(consumers\)/).check()
    await page.locator('#depth').fill('12')
    await page.getByRole('button', { name: 'Expand selected' }).click()
    await expect(visible(page)).toContainText('FetchItemComponent')
    await expect(visible(page)).toContainText('dbo.spGetAllItems')
  })

  await test.step('unresolved / not-found nodes are distinct and explain why', async () => {
    await page.getByRole('button', { name: 'Clear' }).click()
    await pick(page, 'GroupReportService.getHeadcount', 'UI_SERVICE_METHOD')
    await page.getByLabel(/Upstream: depends on \(dependencies\)/).check()
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
    await pick(page, 'FetchItemComponent', 'UI_COMPONENT')
    await page.getByLabel(/Upstream: depends on \(dependencies\)/).check()
    await page.locator('#depth').fill('12')
    await page.getByRole('button', { name: 'Expand selected' }).click()
    await expect(visible(page)).toContainText('ItemController.Index()')
    await expect(visible(page)).not.toContainText('dbo.tblItem')      // the path is cut at the INFERRED dispatch hop
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

  if (live) {
    expect(urls.some((u) => u.endsWith('/api/graph')), 'live mode reads the graph from the API').toBe(true)
    expect(urls.some((u) => u.includes('data/graph.json')), 'live mode must not read the snapshot').toBe(false)
  } else {
    expect(urls.some((u) => u.includes('/api/')), 'snapshot mode must not call the API').toBe(false)
  }
  expect(external, 'no request may leave localhost (no CDNs, no telemetry)').toEqual([])
  expect(consoleErrors, 'no console errors').toEqual([])
})
