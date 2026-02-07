import os
from datetime import date, timedelta
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
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
    description="Advanced API for accessing professional padel data from Premier Padel. Get player stats, match history, tournament info and more! Perfect for building dashboards, apps or doing your own analysis.",
    version="1.1.0"
)

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

class SearchResult(BaseModel):
    type: str  # 'player', 'pair', 'tournament'
    slug: str
    label: str # Name to display

# --- 3. ENDPOINTS: JUGADORES ---

@app.get("/", tags=["General"])
def home():
    return {
        "message": "Welcome to the VoleAI API - Padel Pro Analytics 🎾",
        "docs": "Go to /docs to try the endpoints"
    }

@app.get("/players", tags=["Players"])
def get_players(skip: int = 0, limit: int = 20, search: Optional[str] = None):
    """List all players. Allows search by name."""
    query = supabase.table("players").select("*")
    
    if search:
        query = query.ilike("name", f"%{search}%")
    
    res = query.range(skip, skip + limit - 1).execute()
    return res.data

@app.get("/players/ranking", tags=["Players"])
def get_players_ranking(limit: int = 50):
    """
    Official player ranking.
    Gets the latest available snapshot and orders by points.
    """
    latest_date_res = supabase.table("dynamic_players") \
        .select("snapshot_date").order("snapshot_date", desc=True).limit(1).execute()
    
    if not latest_date_res.data:
        return []
    
    latest_date = latest_date_res.data[0]['snapshot_date']

    res = supabase.table("dynamic_players") \
        .select("slug, points, race_position") \
        .eq("snapshot_date", latest_date) \
        .order("race_position", desc=False) \
        .limit(limit) \
        .execute()
    
    return res.data

@app.get("/players/{slug}", tags=["Players"])
def get_player_profile(slug: str):
    """Static profile + Current stats"""
    player_res = supabase.table("players").select("*").eq("slug", slug).execute()
    if not player_res.data:
        raise HTTPException(status_code=404, detail="Player not found")
    
    stats_res = supabase.table("dynamic_players") \
        .select("*").eq("slug", slug).order("snapshot_date", desc=True).limit(1).execute()
    
    return {
        "profile": player_res.data[0],
        "current_stats": stats_res.data[0] if stats_res.data else None
    }

@app.get("/pairs", tags=["Pairs"])
def get_pairs_ranking(limit: int = 20):
    """Ranking of active pairs based on points."""
    latest_date_res = supabase.table("dynamic_pairs") \
        .select("snapshot_date").order("snapshot_date", desc=True).limit(1).execute()
    
    if not latest_date_res.data: return []
    latest_date = latest_date_res.data[0]['snapshot_date']

    res = supabase.table("dynamic_pairs") \
        .select("*") \
        .eq("snapshot_date", latest_date) \
        .order("points", desc=True) \
        .limit(limit) \
        .execute()
    return res.data

@app.get("/pairs/{slug:path}/evolution", tags=["Pairs"])
def get_pair_evolution(slug: str):
    """History of points and ranking for charts."""
    res = supabase.table("dynamic_pairs") \
        .select("snapshot_date, points, rank_change, dominance_ratio") \
        .eq("pair_slug", slug) \
        .order("snapshot_date", desc=False) \
        .execute()
    return res.data

@app.get("/matches", tags=["Matches"])
def get_matches(limit: int = 20, tournament_id: Optional[int] = None, date_from: Optional[date] = None):
    """General list of matches with filters."""
    query = supabase.table("matches").select("*").order("date", desc=True)
    
    if tournament_id:
        query = query.eq("tournament_id", tournament_id)
    if date_from:
        query = query.gte("date", date_from)
        
    res = query.limit(limit).execute()
    return res.data

@app.get("/matches/head-to-head", tags=["Matches"])
def get_head_to_head(team1: str, team2: str):
    """
    Compare two pairs/teams.
    Returns all matches where they have played against each other.
    """
    slugs = f"({team1},{team2})"
    
    res = supabase.table("matches") \
        .select("*") \
        .filter("team1_slug", "in", slugs) \
        .filter("team2_slug", "in", slugs) \
        .order("date", desc=True) \
        .execute()

    matches = res.data
    wins_team1 = 0
    wins_team2 = 0
    for m in matches:
        is_t1_home = m['team1_slug'] == team1
        
        if is_t1_home:
            if m['winner_team'] == 1: wins_team1 += 1
            else: wins_team2 += 1
        else:
            if m['winner_team'] == 2: wins_team1 += 1
            else: wins_team2 += 1

    return {
        "summary": {team1: wins_team1, team2: wins_team2, "total_matches": len(matches)},
        "history": matches
    }

@app.get("/tournaments", tags=["Tournaments"])
def get_tournaments(year: int = 2025):
    start = f"{year}-01-01"
    end = f"{year}-12-31"
    
    res = supabase.table("tournaments") \
        .select("*") \
        .gte("start_date", start) \
        .lte("start_date", end) \
        .order("start_date", desc=False) \
        .execute()
    return res.data

@app.get("/analytics/trending", tags=["Analytics"])
def get_trending_players():
    """
    Players who have improved their ranking the most this week.
    """
    latest = supabase.table("dynamic_players").select("snapshot_date").limit(1).order("snapshot_date", desc=True).execute()
    if not latest.data: return []
    target_date = latest.data[0]['snapshot_date']
    
    res = supabase.table("dynamic_players") \
        .select("player_slug, points_change, race_position, players(name)") \
        .eq("snapshot_date", target_date) \
        .gt("points_change", 0) \
        .order("points_change", desc=True) \
        .limit(10) \
        .execute()
    
    return res.data


@app.get("/search", tags=["Analytics"])
def global_search(q: str):
    """
    GLOBAL SEARCH: Searches players, pairs, and tournaments simultaneously.
    Ideal for the frontend search bar.
    """
    results = []
    
    p_res = supabase.table("players").select("slug, name").ilike("name", f"%{q}%").limit(3).execute()
    for p in p_res.data:
        results.append({"type": "player", "slug": p['slug'], "label": p['name']})
        
    pair_res = supabase.table("dynamic_pairs").select("pair_slug").ilike("pair_slug", f"%{q}%").limit(3).execute()
    for pair in pair_res.data:
        label = pair['pair_slug'].replace("-", " ").title()
        results.append({"type": "pair_slug", "slug": pair['pair_slug'], "label": label})
        
    t_res = supabase.table("tournaments").select("tournaments_id, full_name").ilike("full_name", f"%{q}%").limit(3).execute()
    for t in t_res.data:
        results.append({"type": "tournament", "id": str(t['tournaments_id']), "label": t['full_name']})
        
    return results