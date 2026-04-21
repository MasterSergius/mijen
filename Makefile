# Variables
COMPOSE = docker compose
APP_SERVICE = mijen
DB_SERVICE = db

.PHONY: up down restart build rebuild reset logs logs-app logs-db ps shell clean

# Start the project in the background
up:
	$(COMPOSE) up -d

# Stop the project
down:
	$(COMPOSE) down

# Rebuild everything and start
restart: down build up

# Rebuild only the app image and restart it (no DB restart, no volume wipe)
rebuild:
	$(COMPOSE) up --build -d --no-deps $(APP_SERVICE)

# Build or rebuild images
build:
	$(COMPOSE) build

# THE "NUCLEAR" OPTION: wipe everything (including DB volumes) and start fresh
reset:
	$(COMPOSE) down -v
	$(COMPOSE) up --build -d

# View live logs for all services
logs:
	$(COMPOSE) logs -f

# View live logs for the app only
logs-app:
	$(COMPOSE) logs -f $(APP_SERVICE)

# View live logs for the database only
logs-db:
	$(COMPOSE) logs -f $(DB_SERVICE)

# Show status of containers
ps:
	$(COMPOSE) ps

# Jump into the app container for debugging
shell:
	$(COMPOSE) exec $(APP_SERVICE) /bin/bash

# Clean up unused docker objects
clean:
	docker system prune -f
