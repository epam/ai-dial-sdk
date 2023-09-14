POETRY ?= poetry
PORT ?= 5001
IMAGE_NAME ?= aidial-sdk
ARGS=

.PHONY: all install_poetry install serve clean lint format test docker_build docker_run

all: help

install_poetry:
	@./install_poetry.sh; \
	echo "Poetry installed..."

install:
	$(POETRY) install

serve: install
	@source ./load_env.sh; load_env; \
	$(POETRY) run python -m server --port=$(PORT)

clean:
	rm -rf $$($(POETRY) env info --path)
	find . -type d -name __pycache__ | xargs rm -r

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

# Define a variable for the test file path.
TEST_FILE ?= tests/unit_tests/

# Run `make test ARGS="-v --durations=0 -rA"` to see stderr/stdout of each test.
# Run `make test TEST_FILE=tests/unit_tests/test_app.py::test_average` to run a specific test file.
test: install
	$(POETRY) run pytest $(TEST_FILE) $(ARGS)

PLATFORM ?= linux/amd64

docker_test:
	docker build --platform $(PLATFORM) -f Dockerfile.test -t $(IMAGE_NAME):test .
	docker run --platform $(PLATFORM) --rm $(IMAGE_NAME):test

docker_serve:
	docker build --platform $(PLATFORM) -t $(IMAGE_NAME):latest .
	docker run --platform $(PLATFORM) --rm -p $(PORT):5000 $(IMAGE_NAME):latest

help:
	@echo '===================='
	@echo 'install                      - set up virtual env and install project depedencies'
	@echo 'clean                        - clean virtual env and build artifacts'
	@echo '-- LINTING --'
	@echo 'format                       - run code formatters'
	@echo 'lint                         - run linters'
	@echo '-- RUN --'
	@echo 'serve                        - run the server locally'
	@echo 'docker_serve                 - run the server from the docker'
	@echo '-- TESTS --'
	@echo 'test                         - run unit tests'
	@echo 'test TEST_FILE=<test_file>   - run all tests in file'
	@echo 'docker_test                  - run unit tests from the docker'
