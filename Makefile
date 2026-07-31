.PHONY: dev stop

dev:
	docker compose up -d
	turbo dev --filter=dashboard --filter=landing

stop:
	docker compose down
