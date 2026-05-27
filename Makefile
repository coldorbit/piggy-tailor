SHELL := /bin/bash

COMPOSE ?= docker compose
APP_URL ?= http://localhost:5000
LOCAL_PORT ?= 5000

.DEFAULT_GOAL := help

.PHONY: help run up down restart rebuild wait logs ps db shell local install clean

help:
	@echo "ResumeTailor commands"
	@echo ""
	@echo "  make run      Build and start the app with PostgreSQL, then show $(APP_URL)"
	@echo "  make up       Start the Docker Compose app stack"
	@echo "  make down     Stop the Docker Compose app stack"
	@echo "  make restart  Restart the app container"
	@echo "  make rebuild  Rebuild the app image and restart the stack"
	@echo "  make logs     Follow app logs"
	@echo "  make ps       Show container status"
	@echo "  make db       Open a psql shell in the PostgreSQL container"
	@echo "  make shell    Open a shell in the app container"
	@echo "  make local    Run the Flask app locally against DATABASE_URL"
	@echo "  make install  Install Python dependencies locally"
	@echo "  make clean    Stop containers and remove the PostgreSQL volume"

run:
	$(COMPOSE) up --build -d
	@$(MAKE) wait
	@echo ""
	@echo "ResumeTailor is running at $(APP_URL)"

up:
	$(COMPOSE) up -d
	@$(MAKE) wait
	@echo ""
	@echo "ResumeTailor is running at $(APP_URL)"

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart resume-tailor
	@echo ""
	@echo "ResumeTailor restarted at $(APP_URL)"

rebuild:
	$(COMPOSE) up --build -d
	@$(MAKE) wait
	@echo ""
	@echo "ResumeTailor rebuilt and running at $(APP_URL)"

wait:
	@for attempt in {1..30}; do \
		if curl -fsS "$(APP_URL)/api/profiles" >/dev/null 2>&1; then \
			exit 0; \
		fi; \
		sleep 1; \
	done; \
	echo "App did not become ready at $(APP_URL)" >&2; \
	exit 1

logs:
	$(COMPOSE) logs -f resume-tailor

ps:
	$(COMPOSE) ps

db:
	$(COMPOSE) exec postgres psql -U resume_tailor -d resume_tailor

shell:
	$(COMPOSE) exec resume-tailor /bin/bash

local:
	PORT=$(LOCAL_PORT) python3 app.py

install:
	python3 -m pip install -r requirements.txt

clean:
	$(COMPOSE) down -v
