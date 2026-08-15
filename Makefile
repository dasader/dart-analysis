.PHONY: rebuild up down logs migrate ps

# 최신 코드 반영 후 도커 이미지 재빌드·재기동
# --force-recreate: 이미지가 그대로여도 컨테이너를 강제 재생성 → .env 변경분이 확실히
# 반영된다(컨테이너는 생성 시점 env를 물고 있어 env_file만 고치면 조용히 옛 값이 남는다).
rebuild:
	git pull
	docker compose up -d --build --force-recreate
	docker compose ps

# DB 스키마를 코드에 맞춘다(신규 테이블 생성 + 누락 컬럼 추가).
# 앱 시작 시에도 같은 코드가 도므로 평소에는 부를 일이 없다. 컨테이너를 올리기 전에
# 스키마를 먼저 맞춰야 하거나, 마이그레이션만 따로 확인하고 싶을 때 쓴다.
# create_all은 기존 테이블에 컬럼을 못 붙이므로 app/migrate.py의 ADDITIONS가 채운다.
migrate:
	docker compose run --rm backend python -m app.migrate

up:
	docker compose up -d

down:
	docker compose down

ps:
	docker compose ps

logs:
	docker compose logs -f
