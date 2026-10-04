FROM python:3.12-slim-bookworm@sha256:54c85f3c47607a77f32adec749d3c81d1348bf25833671f512b26a9b6d778cb3
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1
RUN apt-get update && apt-get install --yes --no-install-recommends age ca-certificates && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 arcadian && useradd --uid 10001 --gid arcadian --no-create-home arcadian
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir --require-hashes -r requirements.txt
COPY . ./
RUN DJANGO_ENV=local CMS_SECRET=collect-static-only-build-placeholder CMS_ALLOWED_HOSTS=localhost \
    CMS_URL=http://localhost:8055 SITE_ORIGINS=http://localhost:8173 \
    DB_NAME=build DB_USER=build DB_PASSWORD=build DB_HOST=localhost python manage.py collectstatic --noinput \
    && chmod +x entrypoint.sh
USER 10001:10001
EXPOSE 8055
ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--config", "gunicorn.conf.py"]
