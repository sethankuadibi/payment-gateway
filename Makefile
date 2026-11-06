.PHONY: help install check test lint run up down logs

help: ## List available commands
	@awk 'BEGIN {FS = ":.*## "; print "Usage: make <target>\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-10s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install development dependencies
	python -m pip install -e '.[dev]'

check: lint test ## Run all quality checks
test: ## Run tests
	python -m pytest -q
lint: ## Run Ruff
	python -m ruff check .
run: ## Run the gateway locally
	uvicorn payment_gateway.api:app --reload
up: ## Start gateway and bank containers
	docker compose up --build --detach
down: ## Stop containers
	docker compose down
logs: ## Follow gateway logs
	docker compose logs --follow gateway

