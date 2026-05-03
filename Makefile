.PHONY: dev dev-backend dev-frontend test migrate docker-up docker-down

dev-backend:
	.venv/bin/uvicorn backend.main:app --reload --port 8000

dev-frontend:
	cd frontend && npx expo start --web

dev:
	$(MAKE) -j2 dev-backend dev-frontend

migrate:
	docker compose exec backend alembic -c backend/alembic.ini upgrade head

test:
	docker compose exec db psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='communityapp_test'" | grep -q 1 || \
		docker compose exec db psql -U postgres -c "CREATE DATABASE communityapp_test"
	docker compose exec -e ENV=test -e DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/communityapp_test backend pytest backend/tests/ -v

docker-up:
	docker compose up

docker-down:
	docker compose down
