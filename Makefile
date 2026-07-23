ARGS ?=
VENV_DIR ?= .venv
POETRY ?= poetry
POETRY_PYTHON ?= python

# Any non-empty CI value (even 'false' or '0') means that CI is enabled
CI ?=

-include .env.dev
export

all: build

init_env:
	$(if $(CI),,$(POETRY) env use $(POETRY_PYTHON))

install: init_env
	$(POETRY) install --all-extras

build: install
	$(POETRY) build

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
