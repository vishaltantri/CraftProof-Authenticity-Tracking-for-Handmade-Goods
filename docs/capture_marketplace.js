/* CraftProof marketplace workflow screenshots — Part 7 of WORKFLOW_GUIDE.md.
 *
 * Companion to capture_workflow.js. That script covers the studio-to-buyer
 * journey; this one covers the resale: a piece is listed on the partner
 * marketplace ReMarket, sells there, and the sale lands on the certificate.
 *
 * Kept separate on purpose. Re-running capture_workflow.js regenerates all
 * sixteen of its screenshots, which churns the repo for no reason when only
 * the marketplace steps need refreshing.
 *
 * Prerequisites — all three running, with ReMarket holding a completed sale
 * that quotes a CraftProof certificate code:
 *   ReMarket     http://127.0.0.1:8000   (REMARKET_SALE_API_KEY set)
 *   CraftProof   http://127.0.0.1:8002   (REMARKET_API_URL + key set)
 *   frontend     http://localhost:5174
 *
 * Usage:  node capture_marketplace.js <remarket_product_id> <certificate_code>
 * Output: ./screenshots/17..20-*.png
 */
const puppeteer = require('puppeteer-core');
const fs = require('fs');
const path = require('path');

const FE = 'http://localhost:5174';
const RM = 'http://127.0.0.1:8000';
const OUT = path.join(__dirname, 'screenshots');

const PRODUCT_ID = process.argv[2];
const CODE = process.argv[3];
if (!PRODUCT_ID || !CODE) {
  console.error('usage: node capture_marketplace.js <remarket_product_id> <certificate_code>');
  process.exit(1);
}

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

async function shot(page, name, clip) {
  const file = path.join(OUT, name);
  await page.screenshot({ path: file, ...(clip ? { clip, captureBeyondViewport: true } : { fullPage: false }) });
  console.log('  wrote', name);
}

/** Scroll an element into view, then measure it.
 *
 * Measuring in the same evaluate() as scrollIntoView() returns pre-scroll
 * coordinates, because the scroll has not been applied yet when
 * getBoundingClientRect() runs. That silently clips the wrong region. So:
 * scroll, wait, then measure in a second call.
 */
async function clipOf(page, target, pad = 16) {
  const found = await page.evaluate((t) => {
    // A css: prefix selects directly; otherwise match the smallest element
    // whose text starts with the given string.
    const el = t.startsWith('css:')
      ? document.querySelector(t.slice(4))
      : [...document.querySelectorAll('div, section')]
          .filter(e => e.innerText && e.innerText.trim().startsWith(t))
          .sort((a, b) => a.innerText.length - b.innerText.length)[0];
    if (!el) return false;
    el.setAttribute('data-shot-target', '1');
    el.scrollIntoView({ block: 'center', behavior: 'instant' });
    return true;
  }, target);
  if (!found) { console.warn(`  ! no element for "${target}"`); return null; }

  await sleep(600);

  const box = await page.evaluate(() => {
    const el = document.querySelector('[data-shot-target]');
    if (!el) return null;
    const r = el.getBoundingClientRect();
    el.removeAttribute('data-shot-target');
    // page.screenshot({clip}) takes PAGE coordinates, while
    // getBoundingClientRect() reports VIEWPORT coordinates. Without adding the
    // scroll offset the clip lands wherever the page happened to be scrolled
    // to, which is how this quietly captured the wrong section twice.
    return {
      x: r.x + window.scrollX,
      y: r.y + window.scrollY,
      width: r.width,
      height: r.height,
      pageWidth: document.documentElement.scrollWidth,
      pageHeight: document.documentElement.scrollHeight,
    };
  });
  if (!box || box.height < 20) return null;

  const x = Math.max(0, box.x - pad);
  const y = Math.max(0, box.y - pad);
  return {
    x, y,
    width: Math.min(box.pageWidth - x, box.width + pad * 2),
    height: Math.min(box.pageHeight - y, box.height + pad * 2),
  };
}

async function login(page, email, password) {
  await page.goto(FE + '/login', { waitUntil: 'networkidle0' });
  await page.type('input[type="email"]', email);
  await page.type('input[type="password"]', password);
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle0' }).catch(() => {}),
    page.click('button[type="submit"]'),
  ]);
  await sleep(1200);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    headless: 'new',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--force-device-scale-factor=2'],
    defaultViewport: { width: 1440, height: 900, deviceScaleFactor: 2 },
  });
  const page = await browser.newPage();
  page.setDefaultTimeout(30000);

  // ---------- 17. The listing on ReMarket, showing CraftProof history ----------
  // This is the ReMarket -> CraftProof direction: their product page calls
  // our public /api/verify/{code} and renders the ownership record.
  console.log('STEP 17: ReMarket listing with CraftProof history');
  await page.goto(`${RM}/products/${PRODUCT_ID}`, { waitUntil: 'networkidle0' });
  await sleep(2500);                       // let the certificate fetch settle
  await shot(page, '17-remarket-listing.png',
             await clipOf(page, 'css:.certificate-section'));

  // ---------- 18. CraftProof pulls the sale in ----------
  console.log('STEP 18: CraftProof marketplace page');
  await login(page, 'meera@example.com', 'craftproof123');
  await page.goto(FE + '/marketplace', { waitUntil: 'networkidle0' });
  await sleep(1500);
  // Press "Check for new sales" so the screenshot shows a real sync result.
  await page.evaluate(() => {
    const b = [...document.querySelectorAll('button')]
      .find(e => e.innerText.toLowerCase().includes('check for new sales'));
    if (b) b.click();
  });
  await sleep(4000);
  await shot(page, '18-craftproof-marketplace.png');

  // ---------- 19. The certificate carries the sale ----------
  console.log('STEP 19: certificate with the marketplace step');
  await page.goto(`${FE}/c/${CODE}`, { waitUntil: 'networkidle0' });
  await sleep(1800);
  await page.screenshot({ path: path.join(OUT, '19-certificate-marketplace-step.png'),
                          fullPage: true });
  console.log('  wrote 19-certificate-marketplace-step.png');

  // ---------- 20. Checking the seller ----------
  console.log('STEP 20: seller check');
  const input = await page.$('input[placeholder="Seller\'s name"]');
  if (input) {
    await input.click();
    await input.type('Someone Else');
    await page.evaluate(() => {
      const b = [...document.querySelectorAll('button')]
        .find(e => e.innerText.trim().toLowerCase() === 'check');
      if (b) b.click();
    });
    await sleep(2500);
  }
  await shot(page, '20-seller-check.png',
             await clipOf(page, 'Buying this from someone?'));

  await browser.close();
  console.log('done');
})().catch(e => { console.error(e); process.exit(1); });
