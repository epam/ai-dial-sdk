ARGS ?=
VENV_DIR ?= .venv
POETRY ?= $(VENV_DIR)/bin/poetry
POETRY_VERSION ?= 2.1.1

all: build

init_env:
	python -m venv $(VENV_DIR)
	$(VENV_DIR)/bin/pip install poetry==$(POETRY_VERSION) --quiet

install: init_env
	$(POETRY) install --all-extras

build: install
	$(POETRY) build

clean:
	rm -rf $$($(POETRY) env info --path)
	rm -rf .nox
	rm -rf .pytest_cache
	rm -rf dist
	find . -type d -name __pycache__ | xargs rm -r

publish: build
	$(POETRY) publish -u __token__ -p $(PYPI_TOKEN) --skip-existing

lint: install
	$(POETRY) run nox -s lint

format: install
	$(POETRY) run nox -s format

test: install
	$(POETRY) run -- nox -s test $(if $(PYTHON),--python=$(PYTHON),) -- $(ARGS)

test_fast: install
	$(POETRY) run -- nox -s test $(if $(PYTHON),--python=$(PYTHON),) -- -m 'not slow' $(ARGS)

benchmark: install
	python -m benchmark.benchmark_merge_chunks

install_git_hooks: install
	$(VENV_DIR)/bin/pre-commit install

help:
	@echo '===================='
	@echo 'build                        - build the library'
	@echo 'clean                        - clean virtual env and build artifacts'
	@echo 'publish                      - publish the library to Pypi'
	@echo 'install_git_hooks            - install the git hooks'
	@echo '-- LINTING --'
	@echo 'format                       - run code formatters'
	@echo 'lint                         - run linters'
	@echo '-- TESTS --'
	@echo 'test                         - run unit tests'
	@echo 'test_fast                    - run unit tests without slow tests'
	@echo 'test PYTHON=<python_version> - run unit tests with the specific python version'
	@echo 'benchmark                    - run benchmarks'
