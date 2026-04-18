# 설계 문서: 분석 상태 버그 수정 + 기업 태그 기능

**날짜**: 2026-04-18  
**작성자**: Claude Code  
**상태**: 승인됨

---

## 1. 개요

두 가지 작업을 함께 구현한다.

1. **버그 수정**: 분석 큐에 투입(pending)된 직후 상태가 "분석완료"로 잘못 표시되는 문제
2. **신규 기능**: 기업 단위 태그 CRUD + 기업 목록 필터링

---

## 2. 버그 수정: 분석 상태 즉시 완료 표시

### 원인

| 파일 | 위치 | 문제 |
|------|------|------|
| `backend/app/routers/companies.py` | `list_companies` L22 | `Analysis.status` 필터 없이 `max(updated_at)` 집계 → pending 분석도 `latest_analysis_date` 반환 |
| `backend/app/routers/reports.py` | `get_reports` L34 | `Analysis.status` 필터 없이 전체 카운트 → pending 포함 3건이면 "완료" 표시 |

### 수정

- `companies.py`: `.filter(Analysis.status == "completed")` 추가
- `reports.py`: `.filter(Analysis.status == "completed")` 추가
- `CompanyList.tsx` `getStatusBadge`: pending/running 상태를 별도 표시하는 로직은 백엔드 수정만으로 해결되므로 프론트 변경 불필요

---

## 3. 신규 기능: 기업 태그

### 3-1. 데이터 모델

```
Tag
  id          Integer   PK, autoincrement
  name        String    unique, not null
  color       String    not null  (hex, 예: "#3B82F6")
  created_at  DateTime  default utcnow

company_tags  (조인 테이블, SQLAlchemy secondary)
  company_id  Integer   FK → companies.id  ON DELETE CASCADE
  tag_id      Integer   FK → tags.id       ON DELETE CASCADE
  PK          (company_id, tag_id)
```

- `Company` 모델에 `tags = relationship("Tag", secondary="company_tags", back_populates="companies")` 추가
- `Tag` 모델에 `companies = relationship("Company", secondary="company_tags", back_populates="tags")` 추가
- 태그 삭제 시 `company_tags` 행 자동 CASCADE 삭제

### 3-2. 프리셋 색상 팔레트 (12색)

프론트에서만 정의. DB는 hex 문자열 그대로 저장.

| 색상명 | hex |
|--------|-----|
| 파랑 | #3B82F6 |
| 초록 | #22C55E |
| 빨강 | #EF4444 |
| 주황 | #F97316 |
| 보라 | #A855F7 |
| 분홍 | #EC4899 |
| 하늘 | #06B6D4 |
| 노랑 | #EAB308 |
| 남색 | #6366F1 |
| 민트 | #14B8A6 |
| 갈색 | #78716C |
| 회색 | #6B7280 |

### 3-3. API

**태그 관리**

| Method | Path | 설명 |
|--------|------|------|
| GET | `/api/tags` | 전체 태그 목록 |
| POST | `/api/tags` | 태그 생성 `{ name, color }` |
| PUT | `/api/tags/{id}` | 태그 수정 `{ name?, color? }` |
| DELETE | `/api/tags/{id}` | 태그 삭제 (company_tags CASCADE) |

**기업-태그 할당**

| Method | Path | 설명 |
|--------|------|------|
| POST | `/api/companies/{id}/tags/{tag_id}` | 태그 할당 |
| DELETE | `/api/companies/{id}/tags/{tag_id}` | 태그 제거 |

**기업 목록 필터링**

```
GET /api/companies?tag_ids=1,2
```
- `tag_ids` 중 하나라도 포함된 기업 반환 (OR 조건)
- 미전달 시 전체 반환 (기존 동작 유지)

**응답 변경**

`CompanyResponse`에 `tags: list[TagResponse]` 필드 추가.  
기업 목록·상세 모두 태그 포함하여 반환.

```python
class TagResponse(BaseModel):
    id: int
    name: str
    color: str
    created_at: datetime
    model_config = {"from_attributes": True}

class TagCreate(BaseModel):
    name: str
    color: str

class TagUpdate(BaseModel):
    name: str | None = None
    color: str | None = None
```

### 3-4. 프론트엔드

#### 태그 관리 페이지 (`/tags`)

- 네비게이션에 "태그 관리" 메뉴 추가 (기존 메뉴 옆)
- 태그 목록: 색상 칩 + 이름 + 수정/삭제 버튼
- 생성 폼: 이름 입력 + 12색 팔레트 선택 (클릭으로 선택)
- 이름 중복 시 백엔드 409 에러 처리

#### 기업 목록 (`/`)

**검색·필터 영역 레이아웃**

```
데스크톱 (md 이상):
[검색바 flex-1]  [태그1 칩] [태그2 칩] [태그3 칩] ...

모바일 (md 미만):
[검색바 w-full]
[태그1 칩] [태그2 칩] ...  (overflow-x-auto 또는 flex-wrap)
```

- `flex flex-wrap gap-2 items-center` 컨테이너
- 검색바: `flex-1 min-w-0`
- 태그 필터: `flex flex-wrap gap-1.5`
- 선택된 태그: 해당 color 배경 + white 텍스트
- 미선택 태그: outline 스타일 + color 텍스트
- 태그 칩 클릭 → 다중 선택 OR 필터, URL query param(`?tag_ids=1,2`)에 반영
- 태그 0개일 때 필터 행 높이 유지 (레이아웃 점프 방지)
- 각 기업 행: 태그 칩 최대 3개 표시 (초과 시 `+N` 뱃지)

#### 기업 상세 (`/companies/:id`)

- 헤더 영역 기업명 아래(또는 옆)에 현재 태그 칩 나열
- `+ 태그` 버튼 → 드롭다운으로 미생성 태그 목록 표시 → 클릭 즉시 POST 할당
- 태그 칩 내 `×` 버튼 → DELETE 즉시 제거
- 낙관적 업데이트 불필요, API 호출 후 상태 갱신

---

## 4. 구현 범위 외 (명시적 제외)

- 보고서 단위 태그
- 태그 카테고리·정렬
- 태그 자동 생성 (태그 관리 페이지에서 사전 생성 필수)
- URL 슬러그 기반 태그 참조

---

## 5. 구현 순서

1. 버그 수정 (백엔드 2줄)
2. DB 모델 추가 (`Tag`, `company_tags`)
3. 스키마 추가 (`TagResponse`, `TagCreate`, `TagUpdate`)
4. `CompanyResponse`에 `tags` 필드 추가, `companies.py` 쿼리 수정
5. `routers/tags.py` 신규 작성
6. `routers/companies.py`에 태그 할당/제거·필터링 엔드포인트 추가
7. 프론트: `Tag` 타입 추가, API 함수 추가
8. 프론트: `TagSettings.tsx` 태그 관리 페이지
9. 프론트: `CompanyList.tsx` 필터 바 + 태그 칩
10. 프론트: `CompanyDetail.tsx` 인라인 태그 할당 UI
11. 네비게이션 메뉴 추가
