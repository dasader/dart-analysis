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
  await expect(page.getByText('분석 동작과 Gemini LLM 프롬프트를 편집합니다')).toBeVisible()
})

test('설정 화면: 동작 토글은 상태를 드러내고 미로그인 시 잠긴다', async ({ page }) => {
  await page.goto('/settings/prompts')
  await expect(page.getByRole('heading', { name: '동작 설정' })).toBeVisible()

  const extract = page.getByRole('switch', { name: '보고서 구역 추출' })
  await expect(extract).toBeVisible()
  // 켜짐/꺼짐이 보조기술에도 드러나야 한다
  await expect(extract).toHaveAttribute('aria-checked', /true|false/)
  // 관리자 로그인 전에는 바꿀 수 없다
  await expect(extract).toBeDisabled()

  await expect(page.getByRole('switch', { name: '신규 보고서 자동 분석' })).toBeVisible()
})

test('보고서 상세: 없는 보고서로 들어가도 깨지지 않는다', async ({ page }) => {
  const errors = []
  page.on('pageerror', e => errors.push(String(e)))
  await page.goto('/companies/999999/reports/999999', { waitUntil: 'networkidle' })
  await expect(page.getByText('보고서를 찾을 수 없습니다')).toBeVisible()
  await expect(page.getByRole('link', { name: '기업으로 돌아가기' })).toBeVisible()
  expect(errors, '페이지 에러').toEqual([])
})

test('구분선 빠진 표도 실제 표로 렌더된다', async ({ page }) => {
  // 모델이 헤더 아래 |---|를 빠뜨리는 경우가 실측 16%였다. 그래도 표로 보여야 한다.
  const broken = [
    '## 종속회사 목록',
    '| 회사명 | 소재지 | 지분율(%) |',
    '| 두산밥캣 | 미국 | 100.00 |',
    '| 두산에너빌리티베트남 | 베트남 | 100.00 |',
  ].join('\n')

  await page.route('**/api/companies/1', r => r.fulfill({
    json: { id: 1, corp_code: 'X', corp_name: '테스트', stock_code: null,
            is_active: true, created_at: '', updated_at: '', report_count: 1,
            latest_analysis_date: null, tags: [] } }))
  await page.route('**/api/companies/1/reports', r => r.fulfill({
    json: [{ id: 1, company_id: 1, rcept_no: '1', report_name: '사업보고서 (2024.12)',
             report_type: '사업보고서', fiscal_year: 2024, filing_date: '2025-03-19',
             file_path: '/x', downloaded_at: '', created_at: '', analysis_count: 1 }] }))
  await page.route('**/api/reports/1/analyses', r => r.fulfill({
    json: [{ id: 1, company_id: 1, report_id: 1, analysis_type: 'subsidiary',
             status: 'completed', result_json: null, result_summary: broken,
             error_message: null, model_name: 'test', created_at: '',
             updated_at: '2026-08-10T00:00:00' }] }))

  await page.goto('/companies/1/reports/1', { waitUntil: 'networkidle' })

  const table = page.locator('article table')
  await expect(table).toBeVisible()
  await expect(table.locator('tbody tr')).toHaveCount(2)
  await expect(table.locator('th').first()).toHaveText('회사명')
  // 파이프 문자가 본문에 그대로 노출되면 안 된다
  await expect(page.locator('article')).not.toContainText('| 두산밥캣 |')
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

test('구역 추출 실패는 경고 배너와 헤더 배지로 알린다', async ({ page }) => {
  // 실패 목록을 가로채 배너가 뜨는지 본다 (실제 실패를 만들지 않고 표시 경로만 검증)
  await page.route('**/api/batches/extraction-failures', route =>
    route.fulfill({
      json: [{
        report_id: 1, company_id: 1, corp_name: '테스트기업',
        report_name: '사업보고서 (2024.12)', fiscal_year: 2024,
        reason: '보고서에서 필수 구역을 찾지 못했습니다: 사업의 내용.',
        failed_at: '2026-08-09T00:00:00',
      }],
    }))

  await page.goto('/settings/batches')
  const banner = page.getByRole('alert')
  await expect(banner).toContainText('구역 추출 실패 1건')
  // 비용이 나가지 않았다는 사실이 반드시 보여야 한다
  await expect(banner).toContainText('AI에 전달되지 않았습니다')
  await expect(banner.getByRole('link', { name: '테스트기업' })).toBeVisible()
  // 헤더 배지는 다른 화면에서도 보인다
  await expect(page.getByTitle(/구역 추출 실패 1건/)).toBeVisible()
})

test('분석 현황 화면에 콘솔 에러 없음', async ({ page }) => {
  const errors = []
  page.on('console', m => m.type() === 'error' && errors.push(m.text()))
  page.on('pageerror', e => errors.push(String(e)))
  await page.goto('/settings/batches', { waitUntil: 'networkidle' })
  expect(errors, '브라우저 콘솔 에러').toEqual([])
})
