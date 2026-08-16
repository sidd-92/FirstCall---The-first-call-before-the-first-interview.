.PHONY: dev stop restart-backend

dev:
	docker compose up -d
	pnpm dev

stop:
	docker compose down

# Recreates the backend container so it picks up changes to .env (e.g.
# PLATFORM_ADMIN_EMAIL) -- `docker compose restart` does NOT do this, it
# only restarts the process inside the existing container without
# re-reading env_file. Always use this after editing .env.
restart-backend:
	docker compose up -d --build backend
