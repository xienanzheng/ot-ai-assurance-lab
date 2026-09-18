.PHONY: up down logs test build pull-model

up:
	docker compose up --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

build:
	docker compose build

test:
	docker compose --profile test run --build --rm --no-deps test-runner

pull-model:
	ollama pull $${OLLAMA_MODEL:-qwen3:8b}


.PHONY: agents-doctor agents-deploy agents-run
agents-doctor:
	python3 scripts/local_agents.py doctor

agents-deploy:
	python3 scripts/local_agents.py deploy

agents-run:
	python3 scripts/local_agents.py run --worker grid --reviewer safety --reviewer consistency
