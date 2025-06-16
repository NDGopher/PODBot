# Pinnacle / Buckeye +EV Sports Betting Dashboard

## Overview

This project is a real-time sports betting odds dashboard that helps you find and track +EV (positive expected value) betting opportunities across multiple sportsbooks. It features a Flask-based Python backend, a modern JavaScript frontend, and robust scraping and normalization logic to ensure accurate, actionable alerts.

- **Frontend:** Displays live odds, +EV plays, and event cards in a compact, modern UI. Highlights +EV plays in green with a star, and pops up real-time alerts for new opportunities.
- **Backend:** Handles alert ingestion, event state management, odds fetching from Pinnacle, and scraping BetBCK for comparison odds.
- **Scraping/Normalization:** Includes advanced normalization to match team names across different sources, with fuzzy matching and suffix stripping (e.g., "Belarus").

## Features

- Real-time odds and +EV play detection
- Modern, compact dashboard UI (HTML/JS/CSS)
- +EV plays highlighted in green with a star
- Popup alerts for new +EV opportunities (with real-time odds refresh)
- Robust team name normalization and fuzzy matching
- Auto-dismiss and manual dismiss for event cards
- Console logging for NVP changes and +EV popup triggers
- Easy extensibility for new leagues, suffixes, or alert sources

## Setup & Installation

1. **Clone the repository and install dependencies:**
   ```bash
   git clone <your-repo-url>
   cd python_bettor_backend
   pip install -r requirements.txt
   ```

2. **Configuration:**
   - Place your `config.json` in the project root with the necessary API keys and BetBCK credentials.
   - Make sure your odds sources (Pinnacle, BetBCK) are accessible from your environment.

3. **Running the Backend:**
   ```bash
   python server.py
   ```
   The Flask server will start on `http://localhost:5001` by default.

4. **Frontend:**
   - Open `http://localhost:5001` in your browser.
   - The dashboard will auto-refresh and display live events and odds.

## Usage

- **Receiving Alerts:**
  - The backend listens for POST requests to `/pod_alert` with event and odds data.
  - When a new alert is received, the backend fetches Pinnacle odds and scrapes BetBCK for comparison.
  - If a +EV play is detected, it is highlighted and a popup appears.

- **Event Cards:**
  - Each card shows the event, start time, odds, and EV% for each market.
  - +EV plays are green, bold, and starred.
  - Click the X to dismiss an event manually, or wait for auto-dismiss.

- **Popups:**
  - When a new +EV play is detected, a popup appears with real-time odds refresh and a console log.
  - The popup will update odds and EV in real time.

- **Console Logging:**
  - NVP changes and +EV popup triggers are logged in the browser console for transparency and debugging.

## Customization

- **Team Name Normalization:**
  - Edit `utils.py` and `betbck_scraper.py` to add/remove suffixes or aliases for team name matching.
  - Suffixes like `Belarus`, `MLB`, etc., are stripped automatically.

- **Alert Sources:**
  - Integrate with additional alert sources by POSTing to `/pod_alert`.

- **UI Tweaks:**
  - Edit `static/js/realtime.js` and `templates/realtime.html` for UI/UX changes.

## Troubleshooting

- **Timing Issues:**
  - The frontend now displays start times exactly as provided by the backend. If you see a full date/time, check your backend formatting.

- **No +EV Popup:**
  - Ensure the event is new and the EV is above the threshold. Check the browser console for logs.

- **Team Name Mismatches:**
  - Add new suffixes or aliases to the normalization logic if you see missed matches in the logs.

- **Backend Not Starting:**
  - Ensure all dependencies are installed and your `config.json` is present and valid.

## License

MIT License (or your preferred license) 