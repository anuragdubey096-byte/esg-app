import { expect, test } from 'playwright/test'

const USERS = {
  manager: { email: 'manager@example.com', password: 'password123' },
  investor: { email: 'investor@example.com', password: 'password123' },
  company: { email: 'healthyfoods@example.com', password: 'password123' },
}

async function signIn(page, { email, password }) {
  await page.goto('/')
  await page.getByLabel('Email').fill(email)
  await page.getByLabel('Password').fill(password)
  await page.getByRole('button', { name: 'Sign In' }).click()
}

test('admin narrative screen opens in Review Hub', async ({ page }) => {
  await signIn(page, USERS.manager)
  await expect(page.getByRole('link', { name: 'Review Hub' })).toBeVisible()
  await page.getByRole('link', { name: 'Review Hub' }).click()
  await expect(page.getByRole('heading', { name: 'AI ESG Narrative Summary' })).toBeVisible()
  await expect(page.getByText('Narrative Controls')).toBeVisible()
})

test('LP narrative screen opens in Reports', async ({ page }) => {
  await signIn(page, USERS.investor)
  await expect(page.getByRole('link', { name: 'Reports' })).toBeVisible()
  await page.getByRole('link', { name: 'Reports' }).click()
  await expect(page.getByRole('heading', { name: 'LP Narrative Summary' })).toBeVisible()
  await expect(page.getByText('Read-only portfolio narrative for investors')).toBeVisible()
})

test('company narrative screen opens in submission review', async ({ page }) => {
  await signIn(page, USERS.company)
  await expect(page.getByRole('button', { name: /View Submission|Continue Submission/ })).toBeVisible()
  await page.getByRole('button', { name: /View Submission|Continue Submission/ }).click()
  await expect(page.getByRole('button', { name: 'Review and Submit' })).toBeVisible()
  await page.getByRole('button', { name: 'Review and Submit' }).click()
  await expect(page.getByRole('heading', { name: 'Company Confirmation Letter' })).toBeVisible()
})
