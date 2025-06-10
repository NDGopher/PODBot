from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import time
import threading
import traceback
import math

from utils import process_event_odds_for_display
from pinnacle_fetcher import fetch_live_pinnacle_event_odds
from main_logic import process_alert_and_scrape_betbck, clean_pod_team_name_for_search

app = Flask(__name__)
CORS(app, resources={r"/get_active_events_data": {"origins": "*"}})
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

active_events_data_store = {}
EVENT_DATA_EXPIRY_SECONDS = 300
BACKGROUND_REFRESH_INTERVAL_SECONDS = 3
dismissed_event_ids = set()

def background_event_refresher():
    while True:
        try:
            time.sleep(BACKGROUND_REFRESH_INTERVAL_SECONDS)
            current_time = time.time()
            for event_id, event_data in list(active_events_data_store.items()):
                if event_id in dismissed_event_ids:
                    del active_events_data_store[event_id]
                    print(f"[BackgroundRefresher] Removed dismissed Event ID: {event_id}")
                    continue
                if (current_time - event_data.get("alert_arrival_timestamp", 0)) > EVENT_DATA_EXPIRY_SECONDS:
                    del active_events_data_store[event_id]
                    if event_id in dismissed_event_ids:
                        dismissed_event_ids.remove(event_id)
                    print(f"[BackgroundRefresher] Removed expired Event ID: {event_id}")
                    continue
                try:
                    pinnacle_api_result = fetch_live_pinnacle_event_odds(event_id)
                    live_pinnacle_odds_processed = process_event_odds_for_display(pinnacle_api_result.get("data"))
                    if not live_pinnacle_odds_processed.get("data"):
                        print(f"[BackgroundRefresher] No data for Event ID: {event_id}, skipping update")
                        continue
                    event_data["last_pinnacle_data_update_timestamp"] = current_time
                    event_data["pinnacle_data_processed"] = live_pinnacle_odds_processed
                    print(f"[BackgroundRefresher] Updated Pinnacle odds for Event ID: {event_id}")
                except Exception as e:
                    print(f"[BackgroundRefresher] Failed to update Event ID: {event_id}, Error: {e}")
                    traceback.print_exc()
        except Exception as e:
            print(f"[BackgroundRefresher] Critical Error: {e}")
            traceback.print_exc()

@app.route('/pod_alert', methods=['POST'])
def handle_pod_alert():
    try:
        payload = request.json
        event_id_str = str(payload.get("eventId"))
        if not event_id_str:
            return jsonify({"status": "error", "message": "Missing eventId"}), 400

        now = time.time()
        print(f"\n[Server-PodAlert] Received alert for Event ID: {event_id_str} ({payload.get('homeTeam','?')})")

        if event_id_str in active_events_data_store:
            last_processed = active_events_data_store[event_id_str].get("last_pinnacle_data_update_timestamp", 0)
            if (now - last_processed) < 15:
                print(f"[Server-PodAlert] Ignoring duplicate alert for Event ID: {event_id_str}")
                return jsonify({"status": "success", "message": f"Alert for {event_id_str} recently processed."}), 200

        pinnacle_api_result = fetch_live_pinnacle_event_odds(event_id_str)
        live_pinnacle_odds_processed = process_event_odds_for_display(pinnacle_api_result.get("data"))
        league_name = live_pinnacle_odds_processed.get("league_name", payload.get("leagueName", "Unknown League"))
        start_time = live_pinnacle_odds_processed.get("starts", payload.get("startTime", "N/A"))

        pod_home_clean = clean_pod_team_name_for_search(payload.get("homeTeam", ""))
        pod_away_clean = clean_pod_team_name_for_search(payload.get("awayTeam", ""))

        betbck_last_update = None
        if event_id_str not in active_events_data_store:
            print(f"[Server-PodAlert] New event {event_id_str}. Initiating scrape.")
            betbck_result = process_alert_and_scrape_betbck(event_id_str, payload, live_pinnacle_odds_processed)

            if not (betbck_result and betbck_result.get("status") == "success"):
                fail_reason = betbck_result.get("message", "Scraper returned None")
                print(f"[Server-PodAlert] Scrape failed. Dropping alert. Reason: {fail_reason}")
                return jsonify({"status": "error", "message": f"Scrape failed: {fail_reason}"}), 200

            print(f"[Server-PodAlert] Scrape successful. Storing event {event_id_str} for display.")
            betbck_last_update = now
            active_events_data_store[event_id_str] = {
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
        else:
            print(f"[Server-PodAlert] Updating existing event {event_id_str} with fresh Pinnacle data.")
            active_events_data_store[event_id_str]["last_pinnacle_data_update_timestamp"] = now
            active_events_data_store[event_id_str]["pinnacle_data_processed"] = live_pinnacle_odds_processed

        return jsonify({"status": "success", "message": f"Alert for {event_id_str} processed."}), 200

    except Exception as e:
        print(f"[Server-PodAlert] CRITICAL Error in /pod_alert: {e}")
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"Internal server error: {str(e)}"}), 500

@app.route('/get_active_events_data', methods=['GET'])
def get_active_events_data():
    current_time_sec = time.time()
    data_to_send = {}
    for eid, entry in active_events_data_store.items():
        if (current_time_sec - entry.get("alert_arrival_timestamp", 0)) > EVENT_DATA_EXPIRY_SECONDS:
            continue
        bet_data = entry["betbck_data"].get("data", {})
        pinnacle_data = entry["pinnacle_data_processed"].get("data", {})
        home_team = pinnacle_data.get("home", entry["original_alert_details"].get("homeTeam", "Home"))
        away_team = pinnacle_data.get("away", entry["original_alert_details"].get("awayTeam", "Away"))
        league_name = pinnacle_data.get("league_name", entry.get("league_name", "Unknown League"))
        start_time = pinnacle_data.get("starts", entry.get("start_time", "N/A"))
        if isinstance(start_time, (int, float)) and start_time > 1000000000:
            from datetime import datetime
            start_time = datetime.utcfromtimestamp(start_time/1000).strftime('%Y-%m-%d %H:%M')
        allow_draw = False
        if "soccer" in league_name.lower() or "draw" in str(pinnacle_data.get("money_line", {})).lower():
            allow_draw = True
        # Use analyzed potential bets if present
        markets = []
        if bet_data.get("potential_bets_analyzed"):
            for bet in bet_data["potential_bets_analyzed"]:
                # Map keys to expected frontend format
                markets.append({
                    "market": bet.get("market"),
                    "selection": bet.get("sel", bet.get("selection")),
                    "line": bet.get("line", ""),
                    "pinnacle_nvp": bet.get("pin_nvp", "N/A"),
                    "betbck_odds": bet.get("bck_odds", "N/A"),
                    "ev": bet.get("ev", "N/A")
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
    expired_ids = set(active_events_data_store.keys()) - set(data_to_send.keys())
    for eid in expired_ids:
        del active_events_data_store[eid]
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
        dismissed_event_ids.add(event_id)
        if event_id in active_events_data_store:
            del active_events_data_store[event_id]
        return jsonify({'status': 'success', 'message': f'Event {event_id} dismissed.'})
    return jsonify({'status': 'error', 'message': 'No eventId provided.'}), 400

if __name__ == '__main__':
    print("Starting Python Flask server for PODBot...")
    threading.Thread(target=background_event_refresher, daemon=True).start()
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False, threaded=True)