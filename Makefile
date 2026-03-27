.PHONY: install bot server dev test typecheck clean

install:
	poetry install

bot:
	poetry run python -m bot.main

server:
	poetry run uvicorn server.main:app --host 0.0.0.0 --port 8000 --reload

dev:
	cd frontend && npm run dev

typecheck:
	poetry run mypy bot server scripts tests
	cd frontend && npx tsc --noEmit

test:
	poetry run pytest tests/ -v

clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; find . -name "*.pyc" -delete 2>/dev/null; echo "Cleaned"
