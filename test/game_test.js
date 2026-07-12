const { chromium } = require('playwright');
const fs = require('fs');

const VIEWPORT = { width: 375, height: 667 };
const URL = 'http://localhost:8099/';
const TABS = ['life', 'work', 'invest', 'pet', 'more', 'task', 'phone'];
const TAB_NAMES = { life: '首页', work: '工作', invest: '投资', pet: '宠物', more: '成长', task: '成就', phone: '手机' };
const VIEWPORT_CUTOFF = 812;

const results = {
  jsErrors: [],
  months: [],
  tabs: {},
  summary: { passed: 0, failed: 0, issues: [] }
};

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

(async () => {
  const browser = await chromium.launch({ args: ['--no-sandbox', '--disable-blink-features=AutomationControlled'] });
  const context = await browser.newContext({
    viewport: VIEWPORT,
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 Mobile/15E148 Safari/604.1'
  });
  const page = await context.newPage();

  page.on('pageerror', err => {
    results.jsErrors.push({ message: err.message, stack: err.stack?.substring(0, 200), time: new Date().toISOString() });
  });
  page.on('console', msg => {
    if (msg.type() === 'error') {
      results.jsErrors.push({ message: msg.text(), type: 'console-error', time: new Date().toISOString() });
    }
  });

  await page.route('**/xiaomimimo.com/**', async route => {
    await route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify({
        choices: [{ message: { content: '{"npcOpening":"你好","options":[{"text":"选项1"},{"text":"选项2"},{"text":"选项3"},{"text":"选项4"}]}' } }]
      })
    });
  });

  console.log('Navigating to game...');
  await page.goto(URL, { waitUntil: 'domcontentloaded', timeout: 30000 });
  await sleep(1500);

  // Check if there's a saved game to load or start new
  const pageInfo = await page.evaluate(() => {
    const welcome = document.querySelector('.welcome-page');
    const startBtn = document.querySelector('.welcome-page .start-btn');
    const newGameBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('新游戏'));
    const challengeBtn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('开始挑战'));
    
    return {
      welcomeVisible: welcome ? welcome.offsetParent !== null : false,
      startBtnExists: !!startBtn,
      newGameBtnExists: !!newGameBtn,
      challengeBtnExists: !!challengeBtn,
      activePage: document.querySelector('.page.active')?.id || 'none',
      bodyFirstText: document.body.innerText.substring(0, 300)
    };
  });
  console.log('Page info:', JSON.stringify(pageInfo, null, 2));

  // Try clicking 开始挑战 first (as it's the main CTA)
  if (pageInfo.challengeBtnExists) {
    console.log('Clicking 开始挑战...');
    await page.evaluate(() => {
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('开始挑战'));
      if (btn) btn.click();
    });
  } else if (pageInfo.startBtnExists) {
    console.log('Clicking start button...');
    await page.evaluate(() => {
      const btn = document.querySelector('.welcome-page .start-btn');
      if (btn) btn.click();
    });
  }
  await sleep(2000);

  // Check for career selection or other modals that might appear
  let modalInfo = await page.evaluate(() => ({
    modal: document.querySelector('.modal-overlay.show')?.textContent?.substring(0, 50) || 'none',
    headerSub: document.getElementById('headerSub')?.textContent || 'empty',
    activePage: document.querySelector('.page.active')?.id || 'none',
    nextMonthBtnVisible: document.getElementById('nextMonthBtn')?.offsetParent !== null || false
  }));
  console.log('After click state:', JSON.stringify(modalInfo, null, 2));

  // If career selection appears, handle it
  if (modalInfo.modal.includes('职业') || modalInfo.modal.includes('行业')) {
    console.log('Career selection modal detected, selecting first career...');
    await page.evaluate(() => {
      const cards = document.querySelectorAll('.career-card');
      if (cards.length > 0) cards[0].click();
    });
    await sleep(1000);
  }

  // Dismiss any guide overlay
  await page.evaluate(() => {
    const guide = document.querySelector('.guide-overlay.show');
    if (guide) {
      const btn = guide.querySelector('.btn');
      if (btn) btn.click();
    }
  });
  await sleep(500);

  // Check if we need to click startGame
  const gameState = await page.evaluate(() => ({
    headerSub: document.getElementById('headerSub')?.textContent || 'empty',
    activePage: document.querySelector('.page.active')?.id || 'none',
    nextMonthBtnVisible: document.getElementById('nextMonthBtn')?.offsetParent !== null || false,
    G_totalMonths: typeof G !== 'undefined' ? G.totalMonths : 'no G'
  }));
  console.log('Game state check:', JSON.stringify(gameState, null, 2));

  // If still not in game, try direct function call
  if (!gameState.nextMonthBtnVisible) {
    console.log('Directly calling startGame...');
    await page.evaluate(() => {
      if (typeof startGame === 'function') startGame();
    });
    await sleep(2000);
    
    // Check again
    const retry = await page.evaluate(() => ({
      nextMonthBtnVisible: document.getElementById('nextMonthBtn')?.offsetParent !== null || false,
      activePage: document.querySelector('.page.active')?.id || 'none',
      headerSub: document.getElementById('headerSub')?.textContent || 'empty'
    }));
    console.log('After startGame:', JSON.stringify(retry, null, 2));
    
    if (!retry.nextMonthBtnVisible) {
      console.log('Still not in game. Trying to show life page directly...');
      await page.evaluate(() => {
        // Hide welcome page, show app
        const welcome = document.querySelector('.welcome-page');
        if (welcome) welcome.style.display = 'none';
        document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
        const lifePage = document.getElementById('page-life');
        if (lifePage) lifePage.classList.add('active');
        if (typeof refreshAll === 'function') refreshAll();
      });
      await sleep(1000);
    }
  }

  // Try clicking nextMonthBtn with force if needed
  const canAdvance = await page.evaluate(() => {
    const btn = document.getElementById('nextMonthBtn');
    return btn ? btn.offsetParent !== null : false;
  });
  console.log('Can advance months:', canAdvance);

  // Advance 12 months
  for (let month = 1; month <= 12; month++) {
    console.log(`\n--- Month ${month} ---`);
    
    const headerBefore = await page.locator('#headerSub').textContent().catch(() => '');
    console.log(`Before: ${headerBefore}`);

    // Ensure life tab
    await page.evaluate(() => { 
      document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
      const lifePage = document.getElementById('page-life');
      if (lifePage) lifePage.classList.add('active');
      if (typeof refreshAll === 'function') refreshAll();
    });
    await sleep(300);

    // Click with force
    await page.evaluate(() => {
      const btn = document.getElementById('nextMonthBtn');
      if (btn) {
        btn.disabled = false;
        btn.click();
      }
    });
    
    await sleep(1500);

    // Close all overlays
    for (let i = 0; i < 15; i++) {
      const overlays = await page.evaluate(() => ({
        modal: document.querySelectorAll('.modal-overlay.show').length,
        choice: document.querySelectorAll('.choice-overlay.show').length,
        promo: document.querySelectorAll('.promo-overlay.show').length,
        guide: document.querySelectorAll('.guide-overlay.show').length,
        rebirth: document.querySelectorAll('.rebirth-panel.show').length
      }));
      
      const total = overlays.modal + overlays.choice + overlays.promo + overlays.guide + overlays.rebirth;
      if (total === 0) break;
      
      await page.evaluate(() => {
        const btn = document.querySelector('.modal-overlay.show .modal-btns .btn');
        if (btn) btn.click();
        const choice = document.querySelector('.choice-overlay.show .choice-option');
        if (choice) choice.click();
        const escape = document.querySelector('.promo-overlay.show, .guide-overlay.show, .rebirth-panel.show');
        if (escape) escape.classList.remove('show');
      });
      await sleep(400);
    }

    const headerAfter = await page.locator('#headerSub').textContent().catch(() => '');
    console.log(`After: ${headerAfter}`);
    
    const monthMatch = headerAfter.match(/(\d+)月/);
    const displayedMonth = monthMatch ? parseInt(monthMatch[1]) : -1;
    
    results.months.push({
      month,
      headerBefore,
      headerAfter,
      displayedMonth,
      expectedMonth: month,
      passed: displayedMonth === month
    });

    if (displayedMonth !== month) {
      results.summary.failed++;
      results.summary.issues.push(`Month ${month}: expected ${month}, got ${displayedMonth}`);
    } else {
      results.summary.passed++;
    }
  }

  // Test each tab
  console.log('\n--- Testing tabs ---');
  for (const tab of TABS) {
    console.log(`\nTab: ${TAB_NAMES[tab]}`);
    
    await page.evaluate((tabName) => {
      if (typeof switchTab === 'function') switchTab(tabName);
    }, tab);
    await sleep(800);

    // Screenshot
    await page.screenshot({ path: `/home/agentuser/tab_${tab}.png` });

    const btnInfo = await page.evaluate((tabName) => {
      const tabContent = document.getElementById('page-' + tabName);
      if (!tabContent) return { count: 0, buttons: [], error: 'not found' };
      
      const buttons = tabContent.querySelectorAll('button:not([disabled])');
      const visible = [];
      buttons.forEach(btn => {
        const rect = btn.getBoundingClientRect();
        if (rect.width > 0 && rect.height > 0 && rect.top >= 0) {
          visible.push({
            text: btn.textContent.trim().substring(0, 25),
            y: Math.round(rect.top),
            x: Math.round(rect.left),
            w: Math.round(rect.width),
            h: Math.round(rect.height)
          });
        }
      });
      return { count: visible.length, buttons: visible };
    }, tab);

    const withExceed = btnInfo.buttons.map(b => ({ ...b, exceeds: b.y > VIEWPORT_CUTOFF }));
    results.tabs[tab] = {
      name: TAB_NAMES[tab],
      count: btnInfo.count,
      buttons: withExceed,
      exceedingCount: withExceed.filter(b => b.exceeds).length,
      passed: btnInfo.count > 0
    };

    console.log(`  Count: ${btnInfo.count}, Exceed: ${withExceed.filter(b => b.exceeds).length}`);
    if (btnInfo.count === 0) {
      results.summary.failed++;
      results.summary.issues.push(`Tab ${tab}: 0 buttons`);
    } else {
      results.summary.passed++;
    }
  }

  console.log('\n--- JS Errors ---');
  console.log(`Total: ${results.jsErrors.length}`);
  results.jsErrors.slice(0, 15).forEach((e, i) => console.log(`  ${i+1}. ${e.message}`));

  console.log('\n--- Results ---');
  console.log(`Passed: ${results.summary.passed}, Failed: ${results.summary.failed}`);
  results.summary.issues.forEach(i => console.log(`  - ${i}`));

  fs.writeFileSync('/home/agentuser/test_results.json', JSON.stringify(results, null, 2));
  console.log('Saved to /home/agentuser/test_results.json');

  await browser.close();
})();
