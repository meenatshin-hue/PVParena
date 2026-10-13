"""PvP Arena: fight an AI opponent through 10 levels, unlocking fighters and better weapons as you win.

Progress is saved in a SQL database (table pvp_players) through this app, so the browser never talks to the
database itself. Which database is used:
  1. [connections.arena_db] in .streamlit/secrets.toml, if it's there (e.g. Postgres when deployed),
  2. otherwise the DATABASE_URL environment variable,
  3. otherwise a SQLite file, pvp_arena.db, next to this file.

Run with:  streamlit run app.py
"""

import base64
import io
import os
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image, ImageDraw, ImageOps
from sqlalchemy import text

HERE = Path(__file__).parent
ASSETS = HERE / "assets"
FIGHTERS = {"duck", "horse", "puppy", "lion", "shark", "alien"}
WEAPONS = {"sword", "silver_sword", "axe", "chainsaw", "gold_sword"}
# The game expects weapon pictures with the handle at the bottom left; these are drawn the other way round.
HANDLE_BOTTOM_RIGHT = {"gold_sword", "axe", "chainsaw"}

st.set_page_config(page_title="PvP Arena", page_icon="⚔️", layout="wide")

arena = components.declare_component("pvp_arena", path=str(HERE / "arena"))


def cut_out_background(im):
    """Make the solid background around a weapon picture transparent, then crop to the weapon."""
    im = im.convert("RGBA")
    w, h = im.size
    if im.getpixel((0, 0))[3] < 255:  # already transparent
        return im.crop(im.getbbox())
    step = max(1, min(w, h) // 40)
    edge = [(x, 0) for x in range(0, w, step)] + [(x, h - 1) for x in range(0, w, step)]
    edge += [(0, y) for y in range(0, h, step)] + [(w - 1, y) for y in range(0, h, step)]
    # The background is the most common color along the edges; parts of the weapon can touch an edge too.
    colors = [im.getpixel(xy) for xy in edge]
    background = max(set(colors), key=colors.count)
    near = lambda c: sum(abs(a - b) for a, b in zip(c[:3], background[:3])) <= 45
    for xy in edge:
        pixel = im.getpixel(xy)
        if pixel[3] == 255 and near(pixel):
            ImageDraw.floodfill(im, xy, (0, 0, 0, 0), thresh=40)
    return im.crop(im.getbbox() or (0, 0, w, h))


@st.cache_data
def load_art(signature):
    """assets/<name>.png -> data URL. Fighters keep their background; weapons get it cut out."""
    art = {}
    for path in sorted(ASSETS.glob("*.png")):
        im = Image.open(path)
        im = im.convert("RGBA") if path.stem in FIGHTERS else cut_out_background(im)
        if path.stem in HANDLE_BOTTOM_RIGHT:
            im = ImageOps.mirror(im)
        buf = io.BytesIO()
        im.save(buf, "PNG")
        art[path.stem] = "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()
    return art


# ---------- database ----------
# Plain SQL that works in both SQLite and Postgres.
CREATE_TABLE = """
create table if not exists pvp_players (
    id          text primary key,
    name        text not null,
    level       integer not null default 1 check (level between 1 and 10),
    best        integer not null default 0 check (best between 0 and 10),
    fighter     text not null default 'duck',
    weapon      text not null default 'sword',
    fresh       text,
    wins        integer not null default 0,
    losses      integer not null default 0,
    created_at  timestamp not null default current_timestamp,
    updated_at  timestamp not null default current_timestamp
)"""

SAVE_PLAYER = """
insert into pvp_players (id, name, level, best, fighter, weapon, fresh, wins, losses)
values (:id, :name, :level, :best, :fighter, :weapon, :fresh, :wins, :losses)
on conflict (id) do update set
    name = excluded.name, level = excluded.level, best = excluded.best, fighter = excluded.fighter,
    weapon = excluded.weapon, fresh = excluded.fresh, wins = excluded.wins, losses = excluded.losses,
    updated_at = current_timestamp"""


def _has_connection_secrets():
    try:
        return "arena_db" in st.secrets.get("connections", {})
    except Exception:
        return False


@st.cache_resource
def open_database():
    """The database connection, with the pvp_players table created if it's missing."""
    if _has_connection_secrets():
        db = st.connection("arena_db", type="sql")
    else:
        url = os.environ.get("DATABASE_URL") or f"sqlite:///{HERE / 'pvp_arena.db'}"
        if url.startswith("postgres://"):  # some hosts give this older form, which SQLAlchemy doesn't accept
            url = "postgresql://" + url[len("postgres://"):]
        db = st.connection("arena_db", type="sql", url=url)
    with db.session as s:
        s.execute(text(CREATE_TABLE))
        s.commit()
    return db


def player_id(name):
    return name.strip().lower()  # so "Sam" and "sam" are one player


def clean_name(name):
    name = str(name or "").strip()
    if not name or len(name) > 24:
        raise ValueError("the name must be 1 to 24 characters")
    return name


def clean_row(row):
    """Check a save sent by the browser before it goes into the database."""
    def number(key, lo, hi):
        value = row.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
            raise ValueError(f"bad {key}")
        return value

    fresh = row.get("fresh")
    if fresh is not None and fresh not in {f"char:{c}" for c in FIGHTERS} | {f"weapon:{w}" for w in WEAPONS}:
        raise ValueError("bad fresh")
    if row.get("fighter") not in FIGHTERS or row.get("weapon") not in WEAPONS:
        raise ValueError("unknown fighter or weapon")
    name = clean_name(row.get("name"))
    return {"id": player_id(name), "name": name, "level": number("level", 1, 10), "best": number("best", 0, 10),
            "fighter": row["fighter"], "weapon": row["weapon"], "fresh": fresh,
            "wins": number("wins", 0, 2**31 - 1), "losses": number("losses", 0, 2**31 - 1)}


def answer(db, req):
    """Carry out one request from the game: load a player (None if new) or save one."""
    try:
        with db.session as s:
            if req.get("op") == "load":
                found = s.execute(text("select name, level, best, fighter, weapon, fresh, wins, losses "
                                       "from pvp_players where id = :id"),
                                  {"id": player_id(clean_name(req.get("name")))}).mappings().first()
                return {"id": req["id"], "row": dict(found) if found else None}
            if req.get("op") == "save":
                s.execute(text(SAVE_PLAYER), clean_row(req.get("row") or {}))
                s.commit()
                return {"id": req["id"], "row": None}
        return {"id": req["id"], "error": "unknown request"}
    except Exception as e:
        return {"id": req["id"], "error": str(e) or type(e).__name__}


try:
    db = open_database()
except Exception as e:
    db = None
    st.error(f"Couldn't open the database, so progress is saved in this browser only. ({e})")

# The game sends its requests as the component's value; answer each one once, then send the answer back with the render.
req = st.session_state.get("arena")
if db and isinstance(req, dict) and req.get("id") != st.session_state.get("answered"):
    st.session_state.answered = req["id"]
    st.session_state.answer = answer(db, req)

# Re-process the art whenever a file in assets/ is added or changed.
signature = tuple((p.name, p.stat().st_mtime) for p in sorted(ASSETS.glob("*.png")))

st.title("⚔️ PvP Arena")
st.caption("Beat 10 AI opponents in a row. Every win unlocks a new fighter or a better weapon.")
arena(assets=load_art(signature), database=db is not None, answer=st.session_state.get("answer"),
      key="arena", default=None)

with st.expander("How to play"):
    st.markdown(
        """
**Controls** (click the arena first so it hears your keys)

| Action | Keys |
|---|---|
| Move backward / forward | **A** / **D** or **←** / **→** |
| Jump | **W** or **↑** |
| Drop faster | **S** or **↓** |
| Attack | **Click the other player** (they must be within your weapon's reach) |
| Shield | **Space**: blocks every attack for 3 seconds, then needs 30 seconds to recharge |

**Fighters**

| Fighter | Health | Unlocked by |
|---|---|---|
| Duck | 200 xp | Start |
| Horse | 400 xp | Beating level 1 |
| Puppy | 500 xp | Beating level 3 |
| Lion | 700 xp | Beating level 5 |
| Shark | 800 xp | Beating level 7 |
| Alien | 2000 xp | Beating level 9 |

**Weapons**

| Weapon | Damage per hit | Unlocked by |
|---|---|---|
| Sword | 10 xp | Start |
| Silver Sword | 15 xp | Beating level 2 |
| Axe | 20 xp | Beating level 4 |
| Chainsaw | 40 xp | Beating level 6 |
| Legendary Gold Sword | 50 xp | Beating level 8 |

The AI gets faster, hits more often, dodges and shields better each level. Beat level 10 to win.
Your progress is saved under your player name, so you can carry on from any computer.
"""
    )
