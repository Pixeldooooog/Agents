FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV TZ=Asia/Shanghai

WORKDIR /opt/app

COPY requirements/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

COPY pyproject.toml ./pyproject.toml
COPY src ./src
RUN pip install --no-cache-dir -e .
COPY config ./config
COPY apps/web/dist ./apps/web/dist
COPY main.py ./main.py

EXPOSE 8010

CMD ["python", "-m", "agents.interfaces.server"]
