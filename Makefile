# Variables
COMPOSE = docker compose
APP_SERVICE = mijen
DB_SERVICE = db

.PHONY: up down restart build reset logs ps shell clean

# Start the project in the background
up:
	$(COMPOSE) up -d

# Stop the project
down:
	$(COMPOSE) down

# Rebuild and start
restart: down up

# Build or rebuild services
build:
	$(COMPOSE) build

# THE "NUCLEAR" OPTION: Wipe everything (including DB volumes) and start fresh
reset:
	$(COMPOSE) down -v
	$(COMPOSE) up --build -d

# View live logs
logs:
	$(COMPOSE) logs -f

# Show status of containers
ps:
	$(COMPOSE) ps

# Jump into the app container for debugging
shell:
	$(COMPOSE) exec $(APP_SERVICE) /bin/bash

# Clean up unused docker objects
clean:
	docker system prune -f
