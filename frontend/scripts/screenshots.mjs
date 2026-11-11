// Takes the documentation screenshots of the RUNNING built app (start it first: `npm run build && npm run preview`).
// usage: node scripts/screenshots.mjs <output-dir>      Only repo-relative paths and synthetic sample data appear in the pages.
import { chromium } from '@playwright/test'
import fs from 'node:fs'
import path from 'node:path'

const out = path.resolve(process.argv[2] ?? 'screenshots')
fs.mkdirSync(out, { recursive: true })
const base = process.env.EXPLORER_URL ?? 'http://127.0.0.1:4173'
const browser = await chromium.launch()
const page = await browser.newPage({ viewport: { width: 1600, height: 950 }, colorScheme: 'light' })
const visible = page.getByTestId('visible-nodes')
const shot = async (name) => { await page.waitForTimeout(400); await page.screenshot({ path: path.join(out, name) }); console.log('saved', name) }
const pick = async (text, kind) => {
  await page.locator('#search').fill(text)
  await page.getByRole('option', { name: new RegExp(`${text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\s+${kind}`) }).first().click()
}

await page.goto(base)
await page.getByRole('heading', { name: 'Dependency explorer' }).waitFor()

// 1. search with results
await page.locator('#search').fill('FetchItem')
await page.getByRole('listbox').waitFor()
await shot('01-search.png')

// 2. expanded workflow with all three confidence styles: UI service -> request -> endpoint -> interface (inferred dispatch) -> data access -> dynamic SQL (unresolved)
await page.locator('#search').fill('')
await pick('ItemService.getItemById', 'UI_SERVICE_METHOD')
await page.locator('#depth').fill('12')
await page.getByRole('button', { name: 'Expand selected' }).click()
await visible.getByText('ItemDataAccessLayer.GetItemData(int)').waitFor()
await shot('02-expanded-workflow-three-confidence-styles.png')

// 3. side panel: an inferred edge with its reason, evidence, commit and the GitHub link
await visible.getByRole('button', { name: 'ShopApp.Interfaces.IItem.GetItemData(int)' }).click()
await page.getByTestId('node-panel').getByRole('button', { name: /DISPATCHES_TO/ }).click()
await page.getByTestId('edge-panel').waitFor()
await shot('03-side-panel-inferred-edge.png')

// 4. side panel: an unresolved / not-found node with its reason
await visible.getByRole('button', { name: /dynamic\/inline SQL|inline\/dynamic SQL/ }).first().click()
await page.getByTestId('node-panel').waitFor()
await shot('04-side-panel-unresolved-node.png')

// 5. a report page
await page.getByRole('link', { name: 'Reports' }).click()
await page.getByRole('button', { name: /pr-b-view/ }).click()
await page.getByRole('heading', { name: /Impact report: pr-b-view/ }).waitFor()
await shot('05-reports-page.png')

// 6. PR comment preview (simulated)
await page.getByRole('link', { name: 'PR comment preview' }).click()
await page.locator('.sim').waitFor()
await shot('06-pr-comment-preview.png')
await browser.close()
