import { test, expect } from '@playwright/test'

// 이미 떠 있는 frontend(8116)를 상대로 돈다. 실행: ~/code/e2e-headless/run.sh http://localhost:8116 frontend/e2e
// 데이터에 의존하지 않는 셸·라우팅만 검증한다 — 기업 등록·분석은 OpenDART·Gemini 실호출이라 제외.

test('첫 화면: 기업 목록 화면 렌더', async ({ page }) => {
  await page.goto('/')
  await expect(page).toHaveTitle(/기업 DART 분석/)
  await expect(page.getByRole('heading', { name: '분석 대상 기업' })).toBeVisible()
  await expect(page.getByRole('button', { name: '기업 등록' })).toBeVisible()
})

test('내비게이션: 태그 관리 → 설정', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: '태그 관리' }).click()
  await expect(page).toHaveURL(/\/tags$/)
  await expect(page.getByText('기업에 할당할 태그를 미리 정의합니다')).toBeVisible()

  await page.getByRole('link', { name: '설정' }).click()
  await expect(page).toHaveURL(/\/settings\/prompts$/)
  await expect(page.getByText('Gemini LLM 분석에 사용되는 프롬프트를 편집합니다')).toBeVisible()
})

test('관리 기능은 로그인 전 안내를 노출', async ({ page }) => {
  await page.goto('/tags')
  await expect(page.getByText('관리자 로그인이 필요합니다')).toBeVisible()
  await expect(page.getByRole('button', { name: '관리자 로그인' })).toBeVisible()
})

test('첫 화면에 콘솔 에러 없음', async ({ page }) => {
  const errors = []
  page.on('console', m => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', e => errors.push(String(e)))
  await page.goto('/', { waitUntil: 'networkidle' })
  expect(errors, '브라우저 콘솔 에러').toEqual([])
})

test('분석 현황: batch 작업 목록 화면 렌더', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('link', { name: '분석 현황' }).click()
  await expect(page).toHaveURL(/\/settings\/batches$/)
  await expect(page.getByRole('heading', { name: '분석 작업 현황' })).toBeVisible()
  // 데이터 유무와 무관하게 큐 요약은 항상 뜬다
  await expect(page.getByText('제출 대기')).toBeVisible()
})

test('분석 현황 화면에 콘솔 에러 없음', async ({ page }) => {
  const errors = []
  page.on('console', m => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', e => errors.push(String(e)))
  await page.goto('/settings/batches', { waitUntil: 'networkidle' })
  expect(errors, '브라우저 콘솔 에러').toEqual([])
})
