#!/bin/sh
set -eu
umask 077
if [ "${DJANGO_ENV:-production}" = production ] && [ "${CMS_DEPLOYMENT:-managed}" = managed ]; then
  if [ -z "${DB_CA_PEM:-}" ]; then
    echo 'DB_CA_PEM is required for verified PostgreSQL TLS.' >&2
    exit 1
  fi
  printf '%s\n' "$DB_CA_PEM" > /tmp/arcadian-postgres-ca.crt
  export DB_CA_FILE=/tmp/arcadian-postgres-ca.crt
fi
exec "$@"
