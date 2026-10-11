const { chromium } = require('playwright');
const fs = require('fs');

const TEST_COMPANIES = [
  { name: 'Reliance Industries', nseSymbol: 'RELIANCE', bseCode: '500325' },
  { name: 'Tata Consultancy Services', nseSymbol: 'TCS', bseCode: '532540' },
  { name: 'Infosys', nseSymbol: 'INFY', bseCode: '500209' },
  { name: 'HDFC Bank', nseSymbol: 'HDFCBANK', bseCode: '500180' },
  { name: 'ICICI Bank', nseSymbol: 'ICICIBANK', bseCode: '532174' }
];

function formatDate(d) {
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, '0');
  const dd = String(d.getDate()).padStart(2, '0');
  return `${yyyy}${mm}${dd}`;
}

const today = new Date();
const thirtyDaysAgo = new Date();
thirtyDaysAgo.setDate(today.getDate() - 30);

const TO_DATE = formatDate(today);
const FROM_DATE = formatDate(thirtyDaysAgo);

async function fetchJson(page, url) {
  try {
    return await page.evaluate(async (u) => {
      const res = await fetch(u, { headers: { Accept: 'application/json' } });
      if (!res.ok) return { error: `HTTP ${res.status}` };
      return await res.json();
    }, url);
  } catch (err) {
    return { error: err.message };
  }
}

async function safeGoto(page, url) {
  try {
    await page.goto(url, { waitUntil: 'domcontentloaded', timeout: 20000 });
    await page.waitForTimeout(2000);
    return { ok: true };
  } catch (err) {
    return { ok: false, error: err.message };
  }
}

(async () => {
  const browser = await chromium.launch();
  const results = [];

  console.log(`Date range: ${FROM_DATE} to ${TO_DATE}`);

  const nsePage = await browser.newPage();
  const nseNav = await safeGoto(nsePage, 'https://www.nseindia.com');
  console.log('NSE homepage nav:', JSON.stringify(nseNav));

  const bsePage = await browser.newPage();
  const bseNav = await safeGoto(bsePage, 'https://www.bseindia.com');
  console.log('BSE homepage nav:', JSON.stringify(bseNav));

  for (const company of TEST_COMPANIES) {
    console.log(`\n=== ${company.name} ===`);

    let nseData = { error: 'NSE homepage nav failed, skipped' };
    if (nseNav.ok) {
      const nseUrl = `https://www.nseindia.com/api/corporate-announcements?index=equities&symbol=${company.nseSymbol}`;
      nseData = await fetchJson(nsePage, nseUrl);
    }
    console.log(`NSE (${company.nseSymbol}):`, JSON.stringify(nseData).slice(0, 400));

    let bseData = { error: 'BSE homepage nav failed, skipped' };
    if (bseNav.ok) {
      const bseUrl = `https://api.bseindia.com/BseIndiaAPI/api/AnnGetData/w?pageno=1&strCat=-1&strPrevDate=${FROM_DATE}&strScrip=${company.bseCode}&strSearch=P&strToDate=${TO_DATE}&strType=C&subcategory=-1`;
      bseData = await fetchJson(bsePage, bseUrl);
    }
    console.log(`BSE (${company.bseCode}):`, JSON.stringify(bseData).slice(0, 400));

    results.push({ company: company.name, nse: nseData, bse: bseData });
  }

  fs.writeFileSync('debug-results-output.json', JSON.stringify(results, null, 2));
  await browser.close();
  console.log('\nDone. Full output in debug-results-output.json');
})();
