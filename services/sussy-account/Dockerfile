FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv/sussy-account
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --system --home /var/lib/sussy-account --create-home --uid 10001 sussy
COPY app.py entrypoint.py ./
RUN chown -R sussy:sussy /srv/sussy-account /var/lib/sussy-account
# Entrypoint starts as root only to set permissions on a newly-mounted data disk,
# then drops to the dedicated unprivileged service account before Uvicorn starts.
USER root
EXPOSE 8080
ENTRYPOINT ["python", "/srv/sussy-account/entrypoint.py"]
