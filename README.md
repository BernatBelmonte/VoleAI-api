
# 🎾 VoleAI API - Padel Data Analytics Engine

VoleAI is an advanced analytics engine for professional padel. This API serves as the backbone for the VoleAI platform, processing historical match data, player performance, and pair statistics to provide deep insights, Head-to-Head (H2H) comparisons, and dynamic rankings.



## 🚀 Tech Stack

* **Framework:** [FastAPI](https://fastapi.tiangolo.com/) (Python)
* **Database:** [Supabase](https://supabase.com/) (PostgreSQL)
* **Server:** Uvicorn / Gunicorn
* **Deployment:** [Render](https://render.com/)
* **Data Processing:** Custom ETL pipeline for padel match telemetry.

## 📊 Data Architecture

The API interacts with five core tables optimized for high-performance analytical queries:

1.  **`players`**: Static player profiles (biography, country, hand preference, etc.).
2.  **`dynamic_players`**: Time-series data for individual points and official rankings.
3.  **`dynamic_pairs`**: Consolidated pair statistics using the `player1/player2` slug format.
4.  **`matches`**: The core dataset with 30+ columns per match.
5.  **`tournaments`**: Metadata for venues, dates, and categories.