# PvP Arena

A Streamlit game: fight an AI player through 10 levels. Every win unlocks a new fighter or a better weapon. Beat level 10 and the screen says **YOU WIN!**

## Database (saving progress)

Progress is saved in a SQL database under each player's name, so you can carry on from any computer. The game sends each save to `app.py`, and `app.py` writes it to the database, so no database keys ever reach the browser. The `pvp_players` table is created automatically the first time the app runs.

Which database is used:

1. `[connections.arena_db]` in `.streamlit/secrets.toml`, if it's there (see `.streamlit/secrets.toml.example`).
2. Otherwise the `DATABASE_URL` environment variable (many hosts set this for you when you add a Postgres database).
3. Otherwise a SQLite file, `pvp_arena.db`, next to `app.py`. Good for playing on your own computer.

**When you deploy**, use option 1 or 2 with a Postgres database (for example Neon, Supabase or your host's own). Most hosts, including Streamlit Community Cloud, wipe their disk when the app restarts, which would erase a SQLite file and everyone's progress with it.

## Run it

```
pip install -r requirements.txt
streamlit run app.py
```

It opens in your browser at http://localhost:8501. Click the arena once so it hears your keys.

## Deploy to Streamlit Community Cloud

1. Put this folder in a GitHub repository (`.gitignore` keeps your secrets and the local database out of it).
2. At share.streamlit.io, create an app from that repository with `app.py` as the main file.
3. In the app's **Settings > Secrets**, paste the `[connections.arena_db]` section with your Postgres URL.

## Controls

- **A / D** or **← / →**: move backward / forward
- **W** or **↑**: jump
- **S** or **↓**: drop faster
- **Click the other player**: attack (they have to be within your weapon's reach)
- **Space**: shield. It blocks every attack for 3 seconds, then needs 30 seconds to recharge.

## Fighters and weapons

| Fighter | Health | | Weapon | Damage |
|---|---|---|---|---|
| Duck (start) | 200 xp | | Sword (start) | 10 xp |
| Horse | 400 xp | | Silver Sword | 15 xp |
| Puppy | 500 xp | | Axe | 20 xp |
| Lion | 700 xp | | Chainsaw | 40 xp |
| Shark | 800 xp | | Legendary Gold Sword | 50 xp |
| Alien | 2000 xp | | | |

Odd levels unlock a fighter and even levels unlock a weapon. The AI gets faster, hits more often, and dodges and shields better each level.

## Pictures

The pictures are in `assets/`, named after the fighter or weapon (`duck.png`, `gold_sword.png`, ...). To change one, replace the file and refresh the page.
Weapon backgrounds are cut out automatically. Weapon pictures should show the weapon on a diagonal with the handle at the bottom left; `app.py` flips the gold sword, axe and chainsaw, which are drawn the other way round.

## Files

- `app.py`: the Streamlit page; loads the pictures, runs the game, and saves progress to the database
- `arena/index.html`: the game itself (arena, controls, AI, levels), loaded as a Streamlit component
- `assets/`: fighter and weapon pictures
- `.streamlit/secrets.toml`: your database URL (optional)
