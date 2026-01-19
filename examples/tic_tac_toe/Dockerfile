FROM python:3.11-alpine

RUN apk add --no-cache git

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .
RUN python -m pip install -r requirements.txt

WORKDIR /app
COPY . /app

RUN adduser -u 1001 --disabled-password --gecos "" appuser && chown -R appuser /app
USER appuser

# The example creates Pydantic V2 models.
# In order to make them compatible with the models used in the DIAL SDK
# we need to enable the compatibility mode with Pydantic V2 via the env variable:
ENV PYDANTIC_V2=True

EXPOSE 5000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
