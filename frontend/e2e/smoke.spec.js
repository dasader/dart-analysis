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

test('기술: 목록 렌더 + 등록은 관리자만', async ({ page }) => {
  await page.route('**/api/technologies', r => r.fulfill({
    json: [{ id: 1, name: '전고체 배터리', description: '설명', keywords: ['황화물계 고체전해질'],
             max_companies: 3, is_active: true, last_scanned_at: '2026-08-15T00:00:00',
             created_at: '2026-08-15T00:00:00',
             tracked_count: 3, available_count: 6, excluded_count: 21,
             keyword_stats: [], ipc_core: [] }] }))

  await page.goto('/')
  // 기업 목록 본문에도 '기술' 링크가 있어 상단 메뉴로 좁힌다
  await page.getByRole('banner').getByRole('link', { name: '기술', exact: true }).click()
  await expect(page).toHaveURL(/\/technologies$/)
  await expect(page.getByRole('link', { name: '전고체 배터리' })).toBeVisible()
  // 미로그인 상태에서는 등록이 잠긴다
  await expect(page.getByRole('button', { name: '기술 등록' })).toBeDisabled()
})

test('기술 상세: 상태별로 나눠 보여준다', async ({ page }) => {
  const company = (o) => ({
    id: o.id, company_id: o.company_id ?? null, corp_code: null,
    corp_name: o.corp_name ?? null, applicant_name: o.applicant_name,
    patent_count: o.patents, keyword_hits: o.kws ?? [], status: o.status,
    exclude_reason: o.reason ?? null, first_seen_at: null, last_seen_at: null,
    is_new: o.is_new ?? false, is_gone: false,
  })
  await page.route('**/api/technologies/1', r => r.fulfill({
    json: {
      id: 1, name: '전고체 배터리', description: '설명',
      keywords: ['황화물계 고체전해질'], max_companies: 3, is_active: true,
      last_scanned_at: '2026-08-15T00:00:00', created_at: '2026-08-15T00:00:00',
      tracked_count: 1, available_count: 1, excluded_count: 1,
      keyword_stats: [], ipc_core: [],
      companies: [
        company({ id: 1, company_id: 7, corp_name: 'LG화학',
                  applicant_name: '주식회사 엘지화학', patents: 16, kws: ['a', 'b'],
                  status: 'tracked', is_new: true }),
        company({ id: 2, corp_name: '삼성SDI', applicant_name: '삼성에스디아이 주식회사',
                  patents: 18, kws: ['a'], status: 'available' }),
        company({ id: 3, applicant_name: '한국전기연구원', patents: 23, kws: ['a'],
                  status: 'excluded', reason: '법인번호 없음(개인·대학·연구소·외국)' }),
      ],
    } }))

  await page.goto('/technologies/1', { waitUntil: 'networkidle' })
  await expect(page.getByRole('heading', { name: '추적 중 (1)' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '등록 가능 (1)' })).toBeVisible()
  await expect(page.getByRole('heading', { name: '제외 (1)' })).toBeVisible()

  // 특허 표기와 DART 표기가 다르다는 걸 드러내야 한다
  await expect(page.getByText('특허: 삼성에스디아이 주식회사')).toBeVisible()
  // 추적 중인 기업은 기업 화면으로 이어진다
  await expect(page.getByRole('link', { name: 'LG화학' })).toHaveAttribute('href', '/companies/7')
  await expect(page.getByText('신규').first()).toBeVisible()
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

test('기업 수정 창은 연 기업의 값으로 채워진다', async ({ page }) => {
  // key 없이 한 번만 만들어 두면 입력칸 초기값이 빈칸·직전 기업 값으로 남아
  // 저장 시 이름과 활성 여부를 덮어썼다(비활성 기업이 다시 켜져 자동 수집 비용이 나간다)
  const co = (id, name, active) => ({ id, corp_code: `0000000${id}`, corp_name: name, stock_code: null,
    jurir_no: null, is_active: active, created_at: '2026-01-01T00:00:00',
    updated_at: '2026-01-01T00:00:00', report_count: 0, latest_analysis_date: null, tags: [] })
  await page.route('**/api/companies', r => r.fulfill({ json: [co(1, '가기업', true), co(2, '나기업', false)] }))
  await page.route('**/api/tags', r => r.fulfill({ json: [] }))
  await page.goto('/')
  const edit = (name) => page.getByRole('row', { name: new RegExp(name) }).getByRole('button', { name: '수정' })
  const nameInput = page.locator('form input[type="text"]').first()

  await edit('가기업').click()
  await expect(nameInput).toHaveValue('가기업')
  await page.getByRole('button', { name: '취소' }).click()

  await edit('나기업').click()
  await expect(nameInput).toHaveValue('나기업')
  await expect(page.locator('form input[type="checkbox"]')).not.toBeChecked()
})
