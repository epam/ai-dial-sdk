all: build

install:
	poetry install --all-extras

build: install
	poetry build

clean:
	rm -rf $$(poetry env info --path)
	rm -rf .nox
	rm -rf .pytest_cache
	rm -rf dist
	find . -type d -name __pycache__ | xargs rm -r

publish: build
	poetry publish -u __token__ -p ${PYPI_TOKEN} --skip-existing

lint: install
	poetry run nox -s lint

format: install
	poetry run nox -s format

test: install
	poetry run nox -s test $(if $(PYTHON),--python=$(PYTHON),)

help:
	@echo '===================='
	@echo 'build                        - build the library'
	@echo 'clean                        - clean virtual env and build artifacts'
	@echo 'publish                      - publish the library to Pypi'
	@echo '-- LINTING --'
	@echo 'format                       - run code formatters'
	@echo 'lint                         - run linters'
	@echo '-- TESTS --'
	@echo 'test                         - run unit tests'
	@echo 'test PYTHON=<python_version> - run unit tests with the specific python version'
