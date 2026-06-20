# Deploy to a sprite (cloud host)

The whole game runs on **one** sprite at a public HTTPS URL. Everyone connects
by browser to that one URL — phones to `/play.html`, the TV to `/display.html`,
the host to `/host.html`. Your laptop does not need to be running.

`SPRITE` is the sprite name (e.g. `sum-beach-trivia`). The sprite CLI must be
installed and authenticated (`sprite login`).

```bash
SPRITE=sum-beach-trivia

# 1. Create the sprite
sprite create "$SPRITE"

# 2. Push the app code into /app (only what the app needs — not .venv/.git/db)
sprite file push -s "$SPRITE" ./app          /app/app
sprite file push -s "$SPRITE" ./static       /app/static
sprite file push -s "$SPRITE" ./deploy       /app/deploy
sprite file push -s "$SPRITE" ./requirements.txt /app/requirements.txt

# 3. Install dependencies on the sprite
sprite exec -s "$SPRITE" -- python3 -m pip install -r /app/requirements.txt

# 4. Put your API key on the sprite's persistent disk (NOT in git, NOT in args).
#    run.sh sources /data/secrets.env automatically.
sprite exec -s "$SPRITE" -- bash -c 'mkdir -p /data && cat > /data/secrets.env' <<'EOF'
ANTHROPIC_API_KEY=sk-ant-your-real-key
# GRADING_MODEL=claude-haiku-4-5   # optional, cheaper grading
EOF

# 5. Register the long-running web service (platform keeps it alive, maps the URL)
sprite exec -s "$SPRITE" -- sprite-env services create web \
  --cmd bash --args /app/deploy/run.sh --http-port 3000

# 6. Make the URL public and print it
sprite url update --auth public -s "$SPRITE"
sprite info -s "$SPRITE"        # URL: https://<sprite>-<org>.sprites.dev/

# 7. Get the host password (reads it from the sprite's database)
sprite exec -s "$SPRITE" -- python3 -c \
  "import sqlite3; r=sqlite3.connect('/data/trivia.db').execute('select code,host_key from game where id=1').fetchone(); print('join code',r[0],'HOST KEY',r[1])"
```

Open the URL from step 6 → the landing page links to all four screens.

## Updating the code later

```bash
sprite file push -s "$SPRITE" ./app    /app/app
sprite file push -s "$SPRITE" ./static /app/static
sprite exec -s "$SPRITE" -- sprite-env services restart web
```

## Notes

- The sprite **auto-sleeps when idle** (free between now and game night) and
  **wakes on the next request**. The SQLite DB and uploaded photos live on the
  persistent disk at `/data`, so they survive sleeps.
- Camera capture on phones needs HTTPS — the sprite URL is HTTPS, so it works.
- Fresh game later: `sprite exec -s "$SPRITE" -- rm -f /data/trivia.db` then
  `sprite exec -s "$SPRITE" -- sprite-env services restart web`.
- Tear down entirely: `sprite destroy "$SPRITE"`.
