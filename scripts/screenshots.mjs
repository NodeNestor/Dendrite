import { chromium } from 'playwright';

const BASE = process.env.BASE_URL || 'http://localhost:8082';

async function main() {
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1920, height: 1080 } });
  const page = await ctx.newPage();

  // 1. Go to History, click the demo tree to load it in Research view
  await page.goto(BASE, { waitUntil: 'networkidle' });
  await page.waitForTimeout(500);

  // Click History
  await page.click('button:has-text("History")');
  await page.waitForTimeout(1000);
  await page.screenshot({ path: 'docs/history.png' });
  console.log('Saved docs/history.png');

  // Click the first tree entry to open it
  const treeEntry = page.locator('.cursor-pointer').first();
  if (await treeEntry.count() > 0) {
    await treeEntry.click();
    await page.waitForTimeout(2000); // wait for tree to render

    // Screenshot the tree view
    await page.screenshot({ path: 'docs/research-tree.png' });
    console.log('Saved docs/research-tree.png');

    // Click a branch node to show the detail sidebar
    const branchNode = page.locator('[class*="cursor-pointer"][class*="rounded-lg"][class*="border"]').first();
    if (await branchNode.count() > 0) {
      await branchNode.click();
      await page.waitForTimeout(500);
      await page.screenshot({ path: 'docs/branch-detail.png' });
      console.log('Saved docs/branch-detail.png');
    }
  } else {
    console.log('No trees found — taking empty research page');
    await page.click('button:has-text("Research")');
    await page.waitForTimeout(500);
    await page.screenshot({ path: 'docs/research-tree.png' });
  }

  // Settings page
  await page.click('button:has-text("Settings")');
  await page.waitForTimeout(1000);
  await page.screenshot({ path: 'docs/settings.png' });
  console.log('Saved docs/settings.png');

  await browser.close();
  console.log('Done!');
}

main().catch(e => { console.error(e); process.exit(1); });
