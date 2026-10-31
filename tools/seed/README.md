# Seed data

Idempotent seed for development and staging. Running it twice changes nothing, as long as it
is within the same season window. A run in a later week (after the season ended or once its
range no longer overlaps) creates a new season.

```bash
export FLOORWARS_DATABASE_URL=postgresql+psycopg://...   # migrated database (alembic upgrade head)
python tools/seed/seed.py
```

It creates:

- 2 buildings with **placeholder hexagonal footprints** (about 25 m radius) near UPT, Timisoara,
  named `Placeholder A/B (UPT, replace with real footprint)`. Buildings are matched by name.
- 5 teams: AC, ETC, MEC, CHIM, CONSTR, each with a distinct colour. Matched by `code`.
- 1 season from Monday 00:00 UTC of the current week, for 14 days. Skipped if a season already
  overlaps that range (the table forbids overlapping seasons).

It never creates users or team memberships.

## Replacing the footprints

The hexagons are not real building outlines. To use real ones, update the rows (keep the ids,
because printed QR codes carry the building id):

```sql
UPDATE building
SET name = 'Real name',
    footprint = ST_GeomFromText('POLYGON((lon lat, ...))', 4326)
WHERE id = 1;
```

The polygon must be closed, valid (`ST_IsValid`) and in SRID 4326, longitude first. Note that the
seed matches buildings by name, so after renaming, a later seed run would insert the placeholders
again. Remove or edit the `BUILDINGS` list in `seed.py` at the same time.

## Tests

`pytest -q tools/seed` needs `FLOORWARS_TEST_DATABASE_URL` (a throwaway, migrated database) and is
skipped without it.

## On the VM (staging)

The server image already contains SQLAlchemy and psycopg, so the seed runs inside the `migrate`
container, which has the migration role's URL as the secret file
`/run/secrets/floorwars_database_url`. Nothing is passed on the command line, so the password never
appears in the process list or the shell history:

```sh
cd /srv/floorwars/repo/infra && export API_TAG=$(cat /srv/floorwars/current)
sudo -E docker compose --profile tools run --rm --no-deps \
  -v /srv/floorwars/repo/tools/seed:/seed:ro migrate python /seed/seed.py
```

It prints the row counts (`building=2, team=5, season=1`). Running it again changes nothing.
