# Own Postgres image (plan 7.7): postgis 18-3.6 plus pgBackRest (2.60.x from the PGDG repo that
# the base image already uses). The archive_command runs inside this container, so no sidecar.
# Build context: infra/postgres. Local: compose.local.yml builds it; production pulls it from GHCR.
FROM postgis/postgis:18-3.6

RUN apt-get update \
    && apt-get install -y --no-install-recommends pgbackrest \
    && rm -rf /var/lib/apt/lists/* \
    # /textfile is a named volume shared with node_exporter (backup-age metric).
    && mkdir -p /etc/pgbackrest /var/log/pgbackrest /var/spool/pgbackrest /var/lib/pgbackrest /textfile \
    && chown postgres:postgres /var/log/pgbackrest /var/spool/pgbackrest /var/lib/pgbackrest /textfile

COPY fw-entrypoint.sh fw-pgbackrest-conf.sh fw-backup-metric.sh /usr/local/bin/
RUN chmod 0755 /usr/local/bin/fw-entrypoint.sh /usr/local/bin/fw-pgbackrest-conf.sh /usr/local/bin/fw-backup-metric.sh

ENTRYPOINT ["fw-entrypoint.sh"]
CMD ["postgres"]
