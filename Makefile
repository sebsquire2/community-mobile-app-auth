.PHONY: dev dev-backend dev-frontend test migrate docker-up docker-down

dev-backend:
	uvicorn backend.main:app --reload --port 8000

dev-frontend:
	cd frontend && npx expo start --web

dev:
	$(MAKE) -j2 dev-backend dev-frontend

migrate:
	alembic -c backend/alembic.ini upgrade head

test:
	ENV=test pytest backend/tests/ -v

docker-up:
	docker-compose up

docker-down:
	docker-compose down
