import { chromium } from 'playwright'

const baseUrl = process.env.UI_BASE_URL || 'http://127.0.0.1:5173'

const rolePlans = [
  {
    role: 'manager',
    email: 'manager@example.com',
    routes: [
      '/overview',
      '/submissions',
      '/review-hub',
      '/analytics',
      '/alerts-risks',
      '/action-plans',
      '/reports',
      '/admin-settings',
    ],
  },
  {
    role: 'investor',
    email: 'investor@example.com',
    routes: ['/lp/dashboard', '/lp/metrics', '/lp/reports'],
  },
  {
    role: 'company',
    email: 'company@example.com',
    routes: [
      '/company/dashboard',
      '/company/submission',
      '/company/submission/review',
      '/company/action-plans',
      '/company/historical',
    ],
  },
]

const unsafeButtonPattern = /(approve|reject|delete|remove|submit|unlock|validate|regenerate|send|close cycle)/i
const fetchErrorPattern = /(failed to fetch|database server is unreachable|unable to sign in right now)/i

async function login(page, email) {
  await page.goto(baseUrl, { waitUntil: 'domcontentloaded', timeout: 45000 })
  await page.locator('#email').fill(email)
  await page.locator('#password').fill('password123')
  await page.getByRole('button', { name: /sign in/i }).click()
  await page.waitForFunction(
    () => {
      const emailInput = document.querySelector('#email')
      const loginError = document.body?.innerText?.toLowerCase().includes('invalid email or password')
      return (!emailInput || !emailInput.offsetParent) || loginError
    },
    { timeout: 12000 }
  ).catch(() => {})
  await page.waitForTimeout(600)
  const loginVisible = await page.locator('#email').isVisible().catch(() => false)
  if (loginVisible) {
    const body = (await page.locator('body').innerText().catch(() => '')) || ''
    throw new Error(`Login failed for ${email}: ${body.slice(0, 200)}`)
  }
}

async function testRoute(page, route, failures) {
  await page.goto(`${baseUrl}${route}`, { waitUntil: 'domcontentloaded', timeout: 60000 })
  await page.waitForTimeout(900)

  const bodyText = (await page.locator('body').innerText().catch(() => '')) || ''
  if (fetchErrorPattern.test(bodyText)) {
    failures.push(`Fetch error text detected on ${route}`)
  }

  const selectBoxes = page.locator('select:visible')
  const selectCount = await selectBoxes.count()
  for (let i = 0; i < Math.min(4, selectCount); i += 1) {
    try {
      const options = selectBoxes.nth(i).locator('option')
      const optionCount = await options.count()
      if (optionCount > 0) {
        await selectBoxes.nth(i).selectOption({ index: 0 })
      }
    } catch (error) {
      failures.push(`Dropdown interaction failed on ${route}: ${String(error).slice(0, 220)}`)
    }
  }

  const buttons = page.locator('button:visible')
  const buttonCount = await buttons.count()
  let clicked = 0
  for (let i = 0; i < Math.min(buttonCount, 20); i += 1) {
    try {
      const text = ((await buttons.nth(i).innerText()) || '').trim()
      if (!text || unsafeButtonPattern.test(text)) continue
      await buttons.nth(i).click({ timeout: 2500 })
      clicked += 1
      await page.waitForTimeout(250)
      if (clicked >= 3) break
    } catch (error) {
      failures.push(`Button interaction failed on ${route}: ${String(error).slice(0, 220)}`)
    }
  }
}

async function run() {
  const browser = await chromium.launch({ headless: true })
  const summary = []
  let totalFailures = 0

  for (const plan of rolePlans) {
    const context = await browser.newContext()
    const page = await context.newPage()
    const failures = []
    const apiErrors = []
    const jsErrors = []

    page.on('requestfailed', (request) => {
      const url = request.url()
      const errorText = request.failure()?.errorText || 'unknown'
      if (errorText.includes('ERR_ABORTED')) return
      if (url.includes('/login') || url.includes('/dashboard') || url.includes('/analytics') || url.includes('/reports') || url.includes('/submissions') || url.includes('/company/')) {
        apiErrors.push(`requestfailed ${request.method()} ${url} -> ${errorText}`)
      }
    })

    page.on('response', (response) => {
      const url = response.url()
      if (response.status() >= 500 && (url.includes(':8000') || url.includes('/api'))) {
        apiErrors.push(`HTTP ${response.status()} ${response.request().method()} ${url}`)
      }
    })

    page.on('pageerror', (error) => {
      jsErrors.push(String(error))
    })

    try {
      await login(page, plan.email)
      for (const route of plan.routes) {
        await testRoute(page, route, failures)
      }
    } catch (error) {
      failures.push(String(error))
    }

    if (apiErrors.length) {
      failures.push(...Array.from(new Set(apiErrors)).slice(0, 20))
    }
    if (jsErrors.length) {
      failures.push(...jsErrors.slice(0, 20).map((item) => `pageerror ${item}`))
    }

    summary.push({
      role: plan.role,
      routes_tested: plan.routes.length,
      failures,
    })
    totalFailures += failures.length
    await context.close()
  }

  await browser.close()
  console.log(JSON.stringify({ baseUrl, totalFailures, summary }, null, 2))
  process.exit(totalFailures > 0 ? 1 : 0)
}

run().catch((error) => {
  console.error(error)
  process.exit(1)
})
