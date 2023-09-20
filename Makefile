POETRY ?= poetry
ARGS=

all: help

install:
	$(POETRY) install --all-extras

clean:
	rm -rf $$($(POETRY) env info --path)
	find . -type d -name __pycache__ | xargs rm -r
	rm -rf .nox
	rm -rf .pytest_cache
	rm -rf dist

build: install
	$(POETRY) build

publish: build
	$(POETRY) twine upload -u __token__ -p ${PYPI_TOKEN} --skip-existing dist/*.whl

lint: install
	@error=0; \
	$(POETRY) run pyright || error=1; \
	$(POETRY) run flake8 || error=1; \
	$(POETRY) run make format ARGS="--check" || error=1; \
	if [ $$error -eq 1 ]; then \
		echo "\033[31mLinting has failed. Run 'make format' to fix formatting and fix other errors manually.\033[0m"; \
		exit 1; \
	fi

format: install
	$(POETRY) run autoflake . $(ARGS); \
	$(POETRY) run isort . $(ARGS); \
	$(POETRY) run black . $(ARGS)

test: install
	$(POETRY) run pytest

PLATFORM ?= linux/amd64

help:
	@echo '===================='
	@echo 'install                      - set up virtual env and install project depedencies'
	@echo 'clean                        - clean virtual env and build artifacts'
	@echo 'build                        - build the library'
	@echo 'publish                      - publish the library to Pypi'
	@echo '-- LINTING --'
	@echo 'format                       - run code formatters'
	@echo 'lint                         - run linters'
	@echo '-- TESTS --'
	@echo 'test                         - run unit tests'
