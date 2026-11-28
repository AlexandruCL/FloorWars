"""Create load-test users on a LOCAL stack and print them as JSON for k6 (users.json).

Run inside the api container, which has the app code, the database URL and the signing key:

    docker compose -f docker-compose.yml -f compose.local.yml exec -T api \
        python - 200 < ../tools/k6/seed_users.py > ../tools/k6/users.json

Needs the stack to be migrated. Creates (when missing) two teams, an active season and one
building, then N users `k6-<run>-<i>@load.invalid` with a device, a team (alternating) and a
2-hour QR check-in each. Access tokens last 15 minutes: seed right before a run. NEVER run this
against the production VM. The output holds bearer tokens: keep users.json out of git (.gitignore).
"""

import json
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import text

from app.auth.tokens import build_access_tokens
from app.config import get_settings
from app.db.session import make_engine, make_sessionmaker

SQUARE = "POLYGON((21.2260 45.7470,21.2262 45.7470,21.2262 45.7472,21.2260 45.7472,21.2260 45.7470))"


def main(count: int) -> None:
    settings = get_settings()
    if settings.env == "prod":
        sys.exit("refusing to seed users with FLOORWARS_ENV=prod")
    tokens = build_access_tokens(settings)
    engine = make_engine(settings.database_url.get_secret_value())  # type: ignore[union-attr]
    now = datetime.now(UTC)
    run = uuid.uuid4().hex[:8]
    users = []
    with make_sessionmaker(engine)() as db:
        team_ids = list(db.execute(text("SELECT id FROM team ORDER BY id LIMIT 2")).scalars())
        for code in ("AC", "ETC")[len(team_ids) :]:
            team_ids.append(
                db.execute(
                    text("INSERT INTO team (code, color_hex) VALUES (:c, '#112233') RETURNING id"),
                    {"c": code},
                ).scalar_one()
            )
        season_id = db.execute(
            text("SELECT id FROM season WHERE active_during @> now() ORDER BY id LIMIT 1")
        ).scalar()
        if season_id is None:
            season_id = db.execute(
                text(
                    "INSERT INTO season (active_during) VALUES (tstzrange(:lo, :hi)) RETURNING id"
                ),
                {"lo": now - timedelta(days=1), "hi": now + timedelta(days=60)},
            ).scalar_one()
        building_id = db.execute(text("SELECT id FROM building ORDER BY id LIMIT 1")).scalar()
        if building_id is None:
            building_id = db.execute(
                text(
                    "INSERT INTO building (name, footprint) "
                    "VALUES ('k6', ST_GeomFromText(:w, 4326)) RETURNING id"
                ),
                {"w": SQUARE},
            ).scalar_one()
        for i in range(count):
            email = f"k6-{run}-{i}@load.invalid"
            user_id = db.execute(
                text(
                    'INSERT INTO "user" (email, display_name, terms_accepted_at, age_confirmed_at) '
                    "VALUES (:e, :d, now(), now()) RETURNING id"
                ),
                {"e": email, "d": f"k6-{i}"},
            ).scalar_one()
            device_id = uuid.uuid4()
            db.execute(
                text(
                    "INSERT INTO device (user_id, id, model, has_barometer) "
                    "VALUES (:u, :d, 'k6', true)"
                ),
                {"u": user_id, "d": device_id},
            )
            db.execute(
                text(
                    "INSERT INTO team_membership (user_id, season_id, team_id) VALUES (:u, :s, :t)"
                ),
                {"u": user_id, "s": season_id, "t": team_ids[i % 2]},
            )
            checkin_id = db.execute(
                text(
                    "INSERT INTO checkin (user_id, building_id, method, valid_during) "
                    "VALUES (:u, :b, 'qr', tstzrange(:lo, :hi)) RETURNING id"
                ),
                {
                    "u": user_id,
                    "b": building_id,
                    "lo": now - timedelta(hours=1),
                    "hi": now + timedelta(hours=2),
                },
            ).scalar_one()
            users.append(
                {
                    "token": tokens.issue(user_id),
                    "device_id": str(device_id),
                    "checkin_id": str(checkin_id),
                }
            )
        db.commit()
    engine.dispose()
    print(json.dumps({"building_id": building_id, "users": users}))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 200)
