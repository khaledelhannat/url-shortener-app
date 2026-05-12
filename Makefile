# Variables
COMPOSE = docker compose
APP_SERVICE = app

.PHONY: help up down restart logs ps shell clean test

help: ## Show this help message
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

up: ## Build and start the containers in background
	$(COMPOSE) up -d --build

down: ## Stop and remove containers
	$(COMPOSE) down

restart: ## Restart all containers
	$(COMPOSE) restart

logs: ## Follow logs from all containers
	$(COMPOSE) logs -f

ps: ## Check status of containers
	$(COMPOSE) ps

shell: ## Open a bash shell in the app container
	$(COMPOSE) exec $(APP_SERVICE) /bin/bash

test: ## Run tests inside the container
	$(COMPOSE) exec $(APP_SERVICE) pytest

clean: ## Remove containers, images, and volumes
	$(COMPOSE) down --rmi all --volumes --remove-orphans
