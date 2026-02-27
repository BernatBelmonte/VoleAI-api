import os
from datetime import date
from typing import Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
url: str = os.getenv("SUPABASE_URL")
key: str = os.getenv("SUPABASE_KEY")

if not url or not key:
    raise ValueError("❌ SUPABASE_URL and SUPABASE_KEY must be set in .env file")

supabase: Client = create_client(url, key)

app = FastAPI(
    title="VoleAI API - Padel Pro Analytics",
    description="Advanced API for accessing professional padel data from Premier Padel.",
    version="1.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Pydantic Models ────────────────────────────────────────────────────────

class PlayerStats(BaseModel):
    slug: str
    name: str
    points: int
    rank: int
    partner: Optional[str] = None

class MatchSchema(BaseModel):
    date: date
    round_name: str
    winner_team: int
    score: Optional[str] = None
    team1_slug: str
    team2_slug: str

# ─── General ────────────────────────────────────────────────────────────────

@app.get("/", tags=["General"])
def home():
    return {"message": "VoleAI API 🎾", "docs": "/docs"}

# ─── Players ────────────────────────────────────────────────────────────────
#
# ORDER MATTERS: specific routes must come before generic /{slug} catch-all.
#
#   /players/ranking                          → 2 fixed segments
#   /players/headtohead/{player1}/{player2}   → 4 segments, before /{slug}
#   /players/{slug}/evolution                 → 3 segments, before /{slug}
#   /players/{slug}                           → 2 segments, LAST (catch-all)

@app.get("/players", tags=["Players"])
def get_players(skip: int = 0, limit: int = 20, search: Optional[str] = None):
    """List all players from the static players table. Supports name search."""
    query = supabase.table("players").select("*")
    if search:
        query = query.ilike("name", f"%{search}%")
    res = query.range(skip, skip + limit - 1).execute()
    return res.data


@app.get("/players/ranking", tags=["Players"])
def get_players_ranking(limit: int = 50):
    """Official ranking from dynamic_players (latest snapshot, ordered by points)."""
    latest = supabase.table("dynamic_players") \
        .select("snapshot_date").order("snapshot_date", desc=True).limit(1).execute()
    if not latest.data:
        return []
    latest_date = latest.data[0]["snapshot_date"]
    res = supabase.table("dynamic_players") \
        .select("*, players(*)") \
        .eq("snapshot_date", latest_date) \
        .order("points", desc=True) \
        .limit(limit) \
        .execute()
    return res.data


@app.get("/players/headtohead/{player1}/{player2}", tags=["Players"])
def get_players_head_to_head(player1: str, player2: str):
    """
    Compare two players using their latest dynamic_players stats.
    NOTE: defined before /players/{slug} to avoid route shadowing.
    """
    p1_res = supabase.table("dynamic_players") \
        .select("*, players(*)") \
        .eq("slug", player1) \
        .order("snapshot_date", desc=True) \
        .limit(1).execute()
    p2_res = supabase.table("dynamic_players") \
        .select("*, players(*)") \
        .eq("slug", player2) \
        .order("snapshot_date", desc=True) \
        .limit(1).execute()
    if not p1_res.data:
        raise HTTPException(404, detail=f"Player '{player1}' not found")
    if not p2_res.data:
        raise HTTPException(404, detail=f"Player '{player2}' not found")
    return {"player1": p1_res.data[0], "player2": p2_res.data[0]}


@app.get("/players/{slug}/evolution", tags=["Players"])
def get_player_evolution(slug: str):
    """
    Point/ranking history for a player.
    NOTE: defined before /players/{slug} to avoid route shadowing.
    """
    check = supabase.table("players").select("slug").eq("slug", slug).execute()
    if not check.data:
        raise HTTPException(404, detail="Player not found")
    res = supabase.table("dynamic_players") \
        .select("*").eq("slug", slug).order("snapshot_date", desc=False).execute()
    return res.data


@app.get("/players/{slug}", tags=["Players"])
def get_player_profile(slug: str):
    """Static profile + latest dynamic stats. LAST player route (catch-all)."""
    player = supabase.table("players").select("*").eq("slug", slug).execute()
    if not player.data:
        raise HTTPException(404, detail="Player not found")
    stats = supabase.table("dynamic_players") \
        .select("*").eq("slug", slug).order("snapshot_date", desc=True).limit(1).execute()
    return {
        "profile": player.data[0],
        "current_stats": stats.data[0] if stats.data else None
    }

# ─── Pairs ──────────────────────────────────────────────────────────────────
#
# Pair slugs use '--' (double dash) as separator and NEVER contain '/'.
# Therefore we use plain {pair_slug} (single-segment) instead of {slug:path},
# which eliminates all catch-all conflicts.
#
# ORDER:
#   /pairs/head-to-head       → query params, fixed path, FIRST
#   /pairs/{pair_slug}/evolution → 3 segments, before /{pair_slug}
#   /pairs/{pair_slug}        → 2 segments, LAST (catch-all)

@app.get("/pairs", tags=["Pairs"])
def get_pairs_ranking(limit: int = 20):
    """Pair ranking from dynamic_pairs (latest snapshot)."""
    latest = supabase.table("dynamic_pairs") \
        .select("snapshot_date").order("snapshot_date", desc=True).limit(1).execute()
    if not latest.data:
        return []
    latest_date = latest.data[0]["snapshot_date"]
    res = supabase.table("dynamic_pairs") \
        .select("*, player1:players!player1_slug(*), player2:players!player2_slug(*)") \
        .eq("snapshot_date", latest_date) \
        .order("points", desc=True) \
        .limit(limit).execute()
    return res.data


@app.get("/pairs/head-to-head", tags=["Pairs"])
def get_pairs_head_to_head(slug1: str = Query(...), slug2: str = Query(...)):
    """
    Compare two pairs via dynamic_pairs stats.
    Uses query params (?slug1=&slug2=) to avoid conflicting with /{pair_slug}.
    NOTE: defined before /pairs/{pair_slug} to avoid route shadowing.
    """
    p1_res = supabase.table("dynamic_pairs") \
        .select("*, player1:players!player1_slug(*), player2:players!player2_slug(*)") \
        .eq("pair_slug", slug1) \
        .order("snapshot_date", desc=True).limit(1).execute()
    p2_res = supabase.table("dynamic_pairs") \
        .select("*, player1:players!player1_slug(*), player2:players!player2_slug(*)") \
        .eq("pair_slug", slug2) \
        .order("snapshot_date", desc=True).limit(1).execute()
    if not p1_res.data:
        raise HTTPException(404, detail=f"Pair '{slug1}' not found")
    if not p2_res.data:
        raise HTTPException(404, detail=f"Pair '{slug2}' not found")
    return {
        "snapshot_date": p1_res.data[0].get("snapshot_date"),
        "pair1": p1_res.data[0],
        "pair2": p2_res.data[0]
    }


@app.get("/pairs/{pair_slug}/evolution", tags=["Pairs"])
def get_pair_evolution(pair_slug: str):
    """
    Point/ranking history for a pair.
    NOTE: defined before /pairs/{pair_slug} to avoid route shadowing.
    """
    res = supabase.table("dynamic_pairs") \
        .select("*").eq("pair_slug", pair_slug).order("snapshot_date", desc=False).execute()
    return res.data


@app.get("/pairs/{pair_slug}", tags=["Pairs"])
def get_pair_profile(pair_slug: str):
    """Pair profile from dynamic_pairs (latest snapshot). LAST pair route (catch-all)."""
    latest = supabase.table("dynamic_pairs") \
        .select("snapshot_date").order("snapshot_date", desc=True).limit(1).execute()
    if not latest.data:
        raise HTTPException(404, detail="No pairs data")
    latest_date = latest.data[0]["snapshot_date"]
    res = supabase.table("dynamic_pairs") \
        .select("*, player1:players!player1_slug(*), player2:players!player2_slug(*)") \
        .eq("pair_slug", pair_slug).eq("snapshot_date", latest_date).execute()
    if not res.data:
        raise HTTPException(404, detail="Pair not found")
    return res.data[0]

# ─── Matches ────────────────────────────────────────────────────────────────
#
# Pair slugs don't contain '/', so plain {pair1}/{pair2} works fine.
# No :path modifier needed.

@app.get("/matches", tags=["Matches"])
def get_matches(limit: int = 20, tournament_id: Optional[int] = None, date_from: Optional[date] = None):
    """List matches with optional filters."""
    query = supabase.table("matches").select("*").order("date", desc=True)
    if tournament_id:
        query = query.eq("tournament_id", tournament_id)
    if date_from:
        query = query.gte("date", date_from)
    return query.limit(limit).execute().data


@app.get("/matches/{pair1}/{pair2}", tags=["Matches"])
def get_matches_head_to_head(pair1: str, pair2: str):
    """Match history between two pairs/teams."""
    slugs = f"({pair1},{pair2})"
    res = supabase.table("matches") \
        .select("*") \
        .filter("team1_slug", "in", slugs) \
        .filter("team2_slug", "in", slugs) \
        .order("date", desc=True).execute()
    matches = res.data
    wins1, wins2 = 0, 0
    for m in matches:
        is_p1_home = m["team1_slug"] == pair1
        if is_p1_home:
            if m["winner_team"] == 1: wins1 += 1
            else: wins2 += 1
        else:
            if m["winner_team"] == 2: wins1 += 1
            else: wins2 += 1
    return {"summary": {pair1: wins1, pair2: wins2, "total_matches": len(matches)}, "history": matches}

# ─── Tournaments ────────────────────────────────────────────────────────────

@app.get("/tournaments", tags=["Tournaments"])
def get_tournaments(year: int = 2025):
    res = supabase.table("tournaments") \
        .select("*") \
        .gte("start_date", f"{year}-01-01") \
        .lte("start_date", f"{year}-12-31") \
        .order("start_date", desc=False).execute()
    return res.data

# ─── Analytics ──────────────────────────────────────────────────────────────

@app.get("/analytics/trending", tags=["Analytics"])
def get_trending_players():
    """Top 10 players with biggest positive points change in the latest snapshot."""
    latest = supabase.table("dynamic_players") \
        .select("snapshot_date").order("snapshot_date", desc=True).limit(1).execute()
    if not latest.data:
        return []
    target_date = latest.data[0]["snapshot_date"]
    res = supabase.table("dynamic_players") \
        .select("*").eq("snapshot_date", target_date) \
        .gt("points_change", 0).order("points_change", desc=True).limit(10).execute()
    return res.data


@app.get("/search", tags=["Analytics"])
def global_search(q: str):
    """Search players, pairs, and tournaments simultaneously."""
    results = []
    for p in supabase.table("players").select("*").ilike("name", f"%{q}%").limit(5).execute().data:
        results.append({"type": "player", "slug": p["slug"], "label": p["name"]})
    for pair in supabase.table("dynamic_pairs").select("pair_slug").ilike("pair_slug", f"%{q}%").limit(5).execute().data:
        label = pair["pair_slug"].replace("--", " / ").replace("-", " ").title()
        results.append({"type": "pair_slug", "slug": pair["pair_slug"], "label": label})
    for t in supabase.table("tournaments").select("*").ilike("full_name", f"%{q}%").limit(3).execute().data:
        results.append({"type": "tournament", "id": str(t["tournaments_id"]), "label": t["full_name"]})
    return results