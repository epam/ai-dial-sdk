POETRY_HOME="/opt/poetry"
POETRY_VERSION="1.6.1"

python3 -m venv ${POETRY_HOME} && \
  $POETRY_HOME/bin/pip install --upgrade pip && \
  $POETRY_HOME/bin/pip install poetry==${POETRY_VERSION}

echo "Poetry version:" && $POETRY_HOME/bin/poetry --version
