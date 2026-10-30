FROM python:3.14.0

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

COPY requirements.txt ./

RUN python -m pip install \
    --no-cache-dir \
    -r requirements.txt

COPY main.py collector.py agents.py common.py ./
COPY mock_ai.py mock_runner.py ./
COPY prompts/ ./prompts/

CMD ["python", "main.py"]