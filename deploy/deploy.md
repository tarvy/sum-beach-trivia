# Deploy to a sprite

1. Create the sprite: `sprite create sum-beach-trivia`
2. Push the code: `sprite file push -s sum-beach-trivia ./ /app`
3. In `sprite console -s sum-beach-trivia`:
   - `cd /app && pip install -r requirements.txt`
   - Set the key: add `ANTHROPIC_API_KEY=...` (and optional `GRADING_MODEL=claude-haiku-4-5`) to the sprite env.
   - `bash deploy/run.sh` (persistent disk at /data keeps the DB + photos across sleeps)
4. Register the web service on port 3000 and make it public: `sprite url -s sum-beach-trivia` to get the public URL.
5. Open the public URL; the server prints the game code + HOST KEY on first start (read it from the console/log).
