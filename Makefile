.PHONY: dev dev-backend dev-frontend test migrate docker-up docker-down help


help: # Show help for each of the Makefile recipes.
	@grep -E '^[a-zA-Z0-9 -]+:.*#'  Makefile | sort | while read -r l; do printf "\033[1;32m$$(echo $$l | cut -f 1 -d':')\033[00m:$$(echo $$l | cut -f 2- -d'#')\n"; done

dev-backend: # Spin up the backend locally
	.venv/bin/uvicorn backend.main:app --reload --port 8000

dev-frontend: # Spin the app frontend on your machine in a browser for user testing
	cd frontend && npx expo start --web

dev: # Spin up both frontend and backend locally
	$(MAKE) -j2 dev-backend dev-frontend

migrate: # Run DB Migrations in docker
	docker compose exec backend alembic -c backend/alembic.ini upgrade head

test: # Run tests in docker
	docker compose exec db psql -U postgres -tc "SELECT 1 FROM pg_database WHERE datname='communityapp_test'" | grep -q 1 || \
		docker compose exec db psql -U postgres -c "CREATE DATABASE communityapp_test"
	docker compose exec -e ENV=test -e DATABASE_URL=postgresql+psycopg://postgres:postgres@db:5432/communityapp_test backend pytest backend/tests/ -v

docker-up: # Spin up backend and db dockers
	docker compose up

docker-down: # Spin down dockers
	docker compose down
