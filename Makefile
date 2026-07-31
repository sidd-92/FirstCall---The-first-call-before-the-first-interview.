.PHONY: dev stop

dev:
	docker compose up -d
	pnpm dev

stop:
	docker compose down
