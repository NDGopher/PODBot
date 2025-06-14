from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import time
import threading
import traceback
import math
import logging
from typing import Dict, Set, Any, Optional
from datetime import datetime, timezone

from utils import process_event_odds_for_display
from pinnacle_fetcher import fetch_live_pinnacle_event_odds
from main_logic import process_alert_and_scrape_betbck, clean_pod_team_name_for_search, american_to_decimal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class StateManager:
    def __init__(self):
        self._active_events_lock = threading.Lock()
        self._dismissed_events_lock = threading.Lock()
        self._active_events: Dict[str, Dict[str, Any]] = {}
        self._dismissed_event_ids: Set[str] = set()
        self.EVENT_DATA_EXPIRY_SECONDS = 300
        self.BACKGROUND_REFRESH_INTERVAL_SECONDS = 3

    def get_active_events(self) -> Dict[str, Dict[str, Any]]:
        with self._active_events_lock:
            return self._active_events.copy()

    def add_active_event(self, event_id: str, event_data: Dict[str, Any]) -> None:
        with self._active_events_lock:
            self._active_events[event_id] = event_data

    def remove_active_event(self, event_id: str) -> None:
        with self._active_events_lock:
            self._active_events.pop(event_id, None)

    def is_event_dismissed(self, event_id: str) -> bool:
        with self._dismissed_events_lock:
            return event_id in self._dismissed_event_ids

    def add_dismissed_event(self, event_id: str) -> None:
        with self._dismissed_events_lock:
            self._dismissed_event_ids.add(event_id)

    def remove_dismissed_event(self, event_id: str) -> None:
        with self._dismissed_events_lock:
            self._dismissed_event_ids.discard(event_id)

    def update_event_data(self, event_id: str, update_data: Dict[str, Any]) -> None:
        with self._active_events_lock:
            if event_id in self._active_events:
                self._active_events[event_id].update(update_data)

state_manager = StateManager()

app = Flask(__name__)
CORS(app)
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

def background_event_refresher():
    while True:
        try:
            time.sleep(state_manager.BACKGROUND_REFRESH_INTERVAL_SECONDS)
            current_time = time.time()
            active_events = state_manager.get_active_events()
            
            for event_id, event_data in list(active_events.items()):
                if state_manager.is_event_dismissed(event_id):
                    state_manager.remove_active_event(event_id)
                    logger.info(f"[BackgroundRefresher] Removed dismissed Event ID: {event_id}")
                    continue
                    
                if (current_time - event_data.get("alert_arrival_timestamp", 0)) > state_manager.EVENT_DATA_EXPIRY_SECONDS:
                    state_manager.remove_active_event(event_id)
                    state_manager.remove_dismissed_event(event_id)
                    logger.info(f"[BackgroundRefresher] Removed expired Event ID: {event_id}")
                    continue
                    
                try:
                    pinnacle_api_result = fetch_live_pinnacle_event_odds(event_id)
                    live_pinnacle_odds_processed = process_event_odds_for_display(pinnacle_api_result.get("data"))
                    if not live_pinnacle_odds_processed.get("data"):
                        logger.info(f"[BackgroundRefresher] No data for Event ID: {event_id}, skipping update")
                        continue
                        
                    state_manager.update_event_data(event_id, {
                        "last_pinnacle_data_update_timestamp": current_time,
                        "pinnacle_data_processed": live_pinnacle_odds_processed
                    })
                    logger.info(f"[BackgroundRefresher] Updated Pinnacle odds for Event ID: {event_id}")
                except Exception as e:
                    logger.error(f"[BackgroundRefresher] Failed to update Event ID: {event_id}, Error: {e}")
                    traceback.print_exc()
        except Exception as e:
            logger.error(f"[BackgroundRefresher] Critical Error: {e}")
            traceback.print_exc()

@app.route('/pod_alert', methods=['POST'])
def handle_pod_alert():
    try:
        payload = request.json
        event_id_str = str(payload.get("eventId"))
        if not event_id_str:
            return jsonify({"status": "error", "message": "Missing eventId"}), 400

        now = time.time()
        logger.info(f"\n[Server-PodAlert] Received alert for Event ID: {event_id_str} ({payload.get('homeTeam','?')})")

        active_events = state_manager.get_active_events()
        if event_id_str in active_events:
            last_processed = active_events[event_id_str].get("last_pinnacle_data_update_timestamp", 0)
            if (now - last_processed) < 15:
                logger.info(f"[Server-PodAlert] Ignoring duplicate alert for Event ID: {event_id_str}")
                return jsonify({"status": "success", "message": f"Alert for {event_id_str} recently processed."}), 200

        pinnacle_api_result = fetch_live_pinnacle_event_odds(event_id_str)
        live_pinnacle_odds_processed = process_event_odds_for_display(pinnacle_api_result.get("data"))
        league_name = live_pinnacle_odds_processed.get("league_name", payload.get("leagueName", "Unknown League"))
        start_time = live_pinnacle_odds_processed.get("starts", payload.get("startTime", "N/A"))

        pod_home_clean = clean_pod_team_name_for_search(payload.get("homeTeam", ""))
        pod_away_clean = clean_pod_team_name_for_search(payload.get("awayTeam", ""))

        betbck_last_update = None
        if event_id_str not in active_events:
            logger.info(f"[Server-PodAlert] New event {event_id_str}. Initiating scrape.")
            betbck_result = process_alert_and_scrape_betbck(event_id_str, payload, live_pinnacle_odds_processed)

            if not (betbck_result and betbck_result.get("status") == "success"):
                fail_reason = betbck_result.get("message", "Scraper returned None")
                logger.error(f"[Server-PodAlert] Scrape failed. Dropping alert. Reason: {fail_reason}")
                return jsonify({"status": "error", "message": f"Scrape failed: {fail_reason}"}), 200

            logger.info(f"[Server-PodAlert] Scrape successful. Storing event {event_id_str} for display.")
            betbck_last_update = now
            event_data = {
                "alert_arrival_timestamp": now,
                "last_pinnacle_data_update_timestamp": now,
                "pinnacle_data_processed": live_pinnacle_odds_processed,
                "original_alert_details": payload,
                "betbck_data": betbck_result,
                "league_name": league_name,
                "start_time": start_time,
                "old_odds": payload.get("oldOdds", "N/A"),
                "new_odds": payload.get("newOdds", "N/A"),
                "no_vig": payload.get("noVigPriceFromAlert", "N/A"),
                "cleaned_home_team": pod_home_clean,
                "cleaned_away_team": pod_away_clean,
                "betbck_last_update": betbck_last_update
            }
            state_manager.add_active_event(event_id_str, event_data)
        else:
            logger.info(f"[Server-PodAlert] Updating existing event {event_id_str} with fresh Pinnacle data.")
            state_manager.update_event_data(event_id_str, {
                "last_pinnacle_data_update_timestamp": now,
                "pinnacle_data_processed": live_pinnacle_odds_processed
            })

        return jsonify({"status": "success", "message": f"Alert for {event_id_str} processed."}), 200

    except Exception as e:
        logger.error(f"[Server-PodAlert] CRITICAL Error in /pod_alert: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Internal server error: {str(e)}"}), 500

@app.route('/get_active_events_data', methods=['GET'])
def get_active_events_data():
    current_time_sec = time.time()
    data_to_send = {}
    for eid, entry in state_manager.get_active_events().items():
        if (current_time_sec - entry.get("alert_arrival_timestamp", 0)) > state_manager.EVENT_DATA_EXPIRY_SECONDS:
            continue
        bet_data = entry["betbck_data"].get("data", {})
        pinnacle_data = entry["pinnacle_data_processed"].get("data", {})
        if not isinstance(pinnacle_data, dict):
            continue  # Skip this event if pinnacle_data is None or not a dict
        home_team = pinnacle_data.get("home", entry["original_alert_details"].get("homeTeam", "Home"))
        away_team = pinnacle_data.get("away", entry["original_alert_details"].get("awayTeam", "Away"))
        league_name = pinnacle_data.get("league_name", entry.get("league_name", "Unknown League"))
        start_time = pinnacle_data.get("starts", entry.get("start_time", "N/A"))
        # Always format start_time as ISO 8601 UTC string if it's a timestamp
        if isinstance(start_time, (int, float)) and start_time > 1000000000:
            # Assume ms timestamp
            dt = datetime.utcfromtimestamp(start_time/1000).replace(tzinfo=timezone.utc)
            start_time = dt.isoformat().replace('+00:00', 'Z')
        elif isinstance(start_time, str):
            try:
                # Try to parse as naive string and convert to UTC ISO
                dt = datetime.strptime(start_time, '%Y-%m-%d %H:%M')
                dt = dt.replace(tzinfo=timezone.utc)
                start_time = dt.isoformat().replace('+00:00', 'Z')
            except Exception:
                pass  # Leave as is if parsing fails
        allow_draw = False
        if "soccer" in league_name.lower() or "draw" in str(pinnacle_data.get("money_line", {})).lower():
            allow_draw = True
        # Use analyzed potential bets if present
        # Initialize markets and re-analyze with latest pinnacle data
        markets = []
        if bet_data.get("potential_bets_analyzed"):
            # Reanalyze with latest pinnacle data to ensure values are up-to-date
            for bet in bet_data["potential_bets_analyzed"]:
                market_type = bet.get("market")
                selection = bet.get("sel", bet.get("selection"))
                line = bet.get("line", "")
                betbck_odds = bet.get("bck_odds", "N/A")
                
                # Re-fetch the current Pinnacle NVP based on market type
                latest_nvp = bet.get("pin_nvp", "N/A")
                
                # Look for updated Pinnacle NVP in the latest data
                pin_periods = pinnacle_data.get("periods", {})
                pin_full_game = pin_periods.get("num_0", {})
                
                # Try to find and update NVP based on market type
                try:
                    if market_type == "ML":
                        pin_ml = pin_full_game.get("money_line", {})
                        if selection == "Home" or selection == bet_data.get("pod_home_team"):
                            latest_nvp = pin_ml.get("nvp_american_home", latest_nvp)
                        elif selection == "Away" or selection == bet_data.get("pod_away_team"):
                            latest_nvp = pin_ml.get("nvp_american_away", latest_nvp)
                        elif selection == "Draw":
                            latest_nvp = pin_ml.get("nvp_american_draw", latest_nvp)
                    elif market_type == "Spread":
                        pin_spreads = pin_full_game.get("spreads", {})
                        # Determine if this is home or away
                        is_home = selection == bet_data.get("pod_home_team")
                        target_hdp = float(line) if is_home else -float(line)
                        for hdp_key, spread_data in pin_spreads.items():
                            if abs(spread_data.get("hdp", 0) - target_hdp) < 0.01:
                                latest_nvp = spread_data.get("nvp_american_home" if is_home else "nvp_american_away", latest_nvp)
                                break
                    elif market_type == "Total":
                        pin_totals = pin_full_game.get("totals", {})
                        target_points = line
                        if target_points in pin_totals:
                            latest_nvp = pin_totals[target_points].get(
                                "nvp_american_over" if selection == "Over" else "nvp_american_under", 
                                latest_nvp
                            )
                    
                    # Recalculate EV with latest NVP
                    if latest_nvp != "N/A" and betbck_odds != "N/A":
                        bet_decimal = american_to_decimal(betbck_odds)
                        true_decimal = american_to_decimal(latest_nvp)
                        from main_logic import calculate_ev
                        ev = calculate_ev(bet_decimal, true_decimal)
                        ev_display = f"{ev*100:.2f}%" if ev is not None else bet.get("ev", "N/A")
                    else:
                        ev_display = bet.get("ev", "N/A")
                        
                    print(f"[GetActiveEvents] Market {market_type} {selection} {line}: Updated NVP from {bet.get('pin_nvp')} to {latest_nvp}")
                except Exception as e:
                    print(f"[GetActiveEvents] Error updating market {market_type} {selection}: {e}")
                    ev_display = bet.get("ev", "N/A")
                    latest_nvp = bet.get("pin_nvp", "N/A")
                
                # Map keys to expected frontend format
                markets.append({
                    "market": market_type,
                    "selection": selection,
                    "line": line,
                    "pinnacle_nvp": latest_nvp,
                    "betbck_odds": betbck_odds,
                    "ev": ev_display
                })
        data_to_send[eid] = {
            "title": f"{home_team} vs {away_team}",
            "meta_info": f"{league_name} | Starts: {start_time}",
            "last_update": entry.get("last_pinnacle_data_update_timestamp", "N/A"),
            "betbck_last_update": entry.get("betbck_last_update", None),
            "alert_description": entry['original_alert_details'].get("betDescription", "POD Alert Processed"),
            "alert_meta": f"(Alert: {entry['old_odds']} → {entry['new_odds']}, NVP: {entry['no_vig']})",
            "betbck_status": f"Data Fetched: {home_team} vs {away_team}" if entry["betbck_data"].get("status") == "success" else entry["betbck_data"].get("message", "Odds check pending..."),
            "markets": markets,
            "alert_arrival_timestamp": entry.get("alert_arrival_timestamp", None)
        }
    expired_ids = set(state_manager.get_active_events().keys()) - set(data_to_send.keys())
    for eid in expired_ids:
        state_manager.remove_active_event(eid)
    print(f"[GetActiveEvents] Returning {len(data_to_send)} active events")
    return jsonify(data_to_send)

@app.route('/')
@app.route('/odds_table')
def odds_table_page_route():
    return render_template('realtime.html')

@app.route('/dismiss_event', methods=['POST'])
def dismiss_event():
    data = request.json
    event_id = str(data.get('eventId'))
    if event_id:
        state_manager.add_dismissed_event(event_id)
        state_manager.remove_active_event(event_id)
        return jsonify({'status': 'success', 'message': f'Event {event_id} dismissed.'})
    return jsonify({'status': 'error', 'message': 'No eventId provided.'}), 400

if __name__ == '__main__':
    logger.info("Starting Python Flask server for PODBot...")
    threading.Thread(target=background_event_refresher, daemon=True).start()
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False, threaded=True)