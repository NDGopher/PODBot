from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import time
import math
from datetime import datetime, timedelta
import threading
import traceback
import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(SCRIPT_DIR, 'config.json')

try:
    from pinnacle_fetcher import fetch_live_pinnacle_event_odds
except ImportError:
    print("ERROR: pinnacle_fetcher.py not found. Using dummy function.")
    def fetch_live_pinnacle_event_odds(event_id):
        return {"success": False, "error": "pinnacle_fetcher.py missing", "data": None}

try:
    from main_logic import process_alert_and_scrape_betbck
    MAIN_LOGIC_AVAILABLE = True
    print("[Server] main_logic.py and process_alert_and_scrape_betbck loaded successfully.")
except Exception as e:
    print(f"[Server] ERROR during import of main_logic: {e}")
    traceback.print_exc()
    MAIN_LOGIC_AVAILABLE = False
    def process_alert_and_scrape_betbck(event_id, original_alert_details, processed_pinnacle_data, scrape_betbck=True):
        return {"status": "main_logic_error", "message": "main_logic.py failed to import."}

app = Flask(__name__)
CORS(app)

active_events_data_store = {}
EVENT_DATA_EXPIRY_SECONDS = 180
BACKGROUND_REFRESH_INTERVAL_SECONDS = 10

def decimal_to_american(decimal_odds):
    if decimal_odds is None or not isinstance(decimal_odds, (float, int)): return "N/A"
    if decimal_odds <= 1.0001: return "N/A"
    if decimal_odds >= 2.0: return f"+{int(round((decimal_odds - 1) * 100))}"
    return f"{int(round(-100 / (decimal_odds - 1)))}"

def process_event_odds_for_display(pinnacle_event_json_data): 
    from utils import calculate_nvp_for_market, decimal_to_american # Assuming these are correctly in utils.py
    if not pinnacle_event_json_data or 'data' not in pinnacle_event_json_data: return {"error": "Invalid or missing 'data'", "success": False, "data": {}}
    event_detail = pinnacle_event_json_data.get('data', {})
    if not isinstance(event_detail, dict): return {"error": "'data' field not a dict", "success": False, "data": {}}
    periods = event_detail.get("periods", {})
    for period_key, period_data in periods.items():
        if not isinstance(period_data, dict): continue
        if period_data.get("money_line") and isinstance(period_data["money_line"], dict):
            ml = period_data["money_line"]
            odds = [ml.get("home"), ml.get("draw"), ml.get("away")]
            nvps = calculate_nvp_for_market(odds)
            ml["nvp_home"], ml["nvp_draw"], ml["nvp_away"] = (nvps[0] if len(nvps)>0 else None), (nvps[1] if len(nvps)>1 else None), (nvps[2] if len(nvps)>2 else None)
            for k in ["home", "draw", "away"]: ml[f"american_{k}"]=decimal_to_american(ml.get(k)); ml[f"nvp_american_{k}"]=decimal_to_american(ml.get(f"nvp_{k}"))
        if period_data.get("spreads") and isinstance(period_data["spreads"], dict):
            for hdp_key, spread_details in period_data["spreads"].items():
                if isinstance(spread_details, dict):
                    if "hdp" not in spread_details: spread_details["hdp"] = hdp_key
                    odds=[spread_details.get("home"),spread_details.get("away")]; nvps=calculate_nvp_for_market(odds)
                    spread_details["nvp_home"],spread_details["nvp_away"]=(nvps[0]if len(nvps)>0 else None),(nvps[1]if len(nvps)>1 else None)
                    for k in ["home","away"]: spread_details[f"american_{k}"]=decimal_to_american(spread_details.get(k)); spread_details[f"nvp_american_{k}"]=decimal_to_american(spread_details.get(f"nvp_{k}"))
        if period_data.get("totals") and isinstance(period_data["totals"], dict):
            for points_key, total_details in period_data["totals"].items():
                if isinstance(total_details, dict):
                    if "points" not in total_details: total_details["points"] = points_key
                    odds=[total_details.get("over"),total_details.get("under")]; nvps=calculate_nvp_for_market(odds)
                    total_details["nvp_over"],total_details["nvp_under"]=(nvps[0]if len(nvps)>0 else None),(nvps[1]if len(nvps)>1 else None)
                    for k in ["over","under"]: total_details[f"american_{k}"]=decimal_to_american(total_details.get(k)); total_details[f"nvp_american_{k}"]=decimal_to_american(total_details.get(f"nvp_{k}"))
    return pinnacle_event_json_data

def background_event_refresher():
    print(f"[BackgroundRefresher] Thread started. Interval: {BACKGROUND_REFRESH_INTERVAL_SECONDS}s")
    while True:
        time.sleep(BACKGROUND_REFRESH_INTERVAL_SECONDS)
        now = time.time()
        for event_id_str in list(active_events_data_store.keys()):
            try:
                entry = active_events_data_store.get(event_id_str)
                if not entry: continue

                pinnacle_api_result = fetch_live_pinnacle_event_odds(str(event_id_str))
                if pinnacle_api_result and pinnacle_api_result.get("success") and pinnacle_api_result.get("data"):
                    live_pinnacle_odds_processed = process_event_odds_for_display(pinnacle_api_result.get("data"))
                    if event_id_str in active_events_data_store:
                        active_events_data_store[event_id_str]["last_pinnacle_data_update_timestamp"] = now
                        active_events_data_store[event_id_str]["pinnacle_processed_data"] = live_pinnacle_odds_processed
                        
                        betbck_data = entry.get("betbck_comparison_data")
                        if betbck_data and betbck_data.get("status") == "success": # Defensive check
                            re_analyzed_result = process_alert_and_scrape_betbck(event_id_str, entry["original_alert_details"], live_pinnacle_odds_processed, scrape_betbck=False)
                            if any(float(bet.get("ev", "0%").strip('%')) > 0 for bet in re_analyzed_result.get("data", {}).get("potential_bets_analyzed", [])):
                                active_events_data_store[event_id_str]['has_ever_been_positive_ev'] = True

                betbck_data = entry.get("betbck_comparison_data")
                if betbck_data and betbck_data.get("status") == "success":
                    last_scrape_time = betbck_data.get("scrape_timestamp", entry.get("alert_arrival_timestamp"))
                    if (now - last_scrape_time) > 60:
                        print(f"[BackgroundRefresher] Re-scraping BetBCK for event {event_id_str}...")
                        active_events_data_store[event_id_str]['is_past_initial_view_period'] = True
                        
                        refreshed_betbck_result = process_alert_and_scrape_betbck(event_id_str, entry["original_alert_details"], entry["pinnacle_processed_data"])
                        if event_id_str in active_events_data_store:
                            refreshed_betbck_result["scrape_timestamp"] = now
                            active_events_data_store[event_id_str]["betbck_comparison_data"] = refreshed_betbck_result
                            if any(float(bet.get("ev", "0%").strip('%')) > 0 for bet in refreshed_betbck_result.get("data", {}).get("potential_bets_analyzed", [])):
                                active_events_data_store[event_id_str]['has_ever_been_positive_ev'] = True
            except Exception as e_bg_refresh:
                print(f"[BackgroundRefresher] CRITICAL Error during refresh of event {event_id_str}: {e_bg_refresh}")
                traceback.print_exc()

@app.route('/pod_alert', methods=['POST'])
def handle_pod_alert():
    event_id_str = None
    try:
        payload = request.json
        event_id = payload.get("eventId")
        if not event_id: return jsonify({"status": "error", "message": "Missing eventId"}), 400
        
        event_id_str = str(event_id)
        now = time.time()
        print(f"\n[Server-PodAlert] Received alert for Event ID: {event_id_str} ({payload.get('homeTeam','?')})")

        pinnacle_api_result = fetch_live_pinnacle_event_odds(event_id_str)
        live_pinnacle_odds_processed = process_event_odds_for_display(pinnacle_api_result.get("data") if pinnacle_api_result else {})

        if event_id_str in active_events_data_store:
            print(f"[Server-PodAlert] Updating existing event {event_id_str}.")
            active_events_data_store[event_id_str]["last_pinnacle_data_update_timestamp"] = now
            active_events_data_store[event_id_str]["pinnacle_processed_data"] = live_pinnacle_odds_processed
        else:
            print(f"[Server-PodAlert] New event {event_id_str}. Storing initial details and initiating scrape.")
            active_events_data_store[event_id_str] = {
                "alert_arrival_timestamp": now,
                "last_pinnacle_data_update_timestamp": now,
                "pinnacle_processed_data": live_pinnacle_odds_processed,
                "original_alert_details": payload,
                "betbck_comparison_data": None,
                'has_ever_been_positive_ev': False,
                'is_past_initial_view_period': False
            }
            
            if MAIN_LOGIC_AVAILABLE:
                betbck_result = process_alert_and_scrape_betbck(
                    event_id_str, 
                    active_events_data_store[event_id_str]["original_alert_details"],
                    live_pinnacle_odds_processed
                )
                
                status_msg = betbck_result.get('status','N/A')
                print(f"[Server-PodAlert] main_logic BetBCK result status for {event_id_str}: {status_msg}")

                if status_msg == "error_betbck_scrape_failed":
                    print(f"[Server-PodAlert] Scrape failed for event {event_id_str}. Removing from display.")
                    if event_id_str in active_events_data_store: del active_events_data_store[event_id_str]
                else:
                    betbck_result["scrape_timestamp"] = now
                    if event_id_str in active_events_data_store:
                        active_events_data_store[event_id_str]["betbck_comparison_data"] = betbck_result
                        potential_bets = betbck_result.get("data", {}).get("potential_bets_analyzed", [])
                        if any(float(bet.get("ev", "0%").strip('%')) > 0 for bet in potential_bets):
                            print(f"[Server-PodAlert] Initial +EV found for event {event_id_str}.")
                            active_events_data_store[event_id_str]['has_ever_been_positive_ev'] = True
        
        return jsonify({"status": "success", "message": f"Alert for {event_id_str} processed."}), 200

    except Exception as e:
        print(f"[Server-PodAlert] CRITICAL Error in /pod_alert: {e}")
        traceback.print_exc()
        if event_id_str and event_id_str in active_events_data_store:
            del active_events_data_store[event_id_str]
            print(f"[Server-PodAlert] Removed event {event_id_str} due to processing error.")
        return jsonify({"status": "error", "message": f"Internal server error: {str(e)}"}), 500

@app.route('/get_active_events_data', methods=['GET'])
def get_active_events_data():
    current_time_sec = time.time()
    data_to_send_to_client = {}
    expired_ids = []
    betbck_main_url = None
    try:
        with open(CONFIG_FILE_PATH, 'r') as f:
            config_data = json.load(f)
        betbck_main_url = config_data.get('betbck', {}).get('main_page_url_after_login')
    except Exception as e:
        print(f"[Server-ActiveEvents] Error reading config for BetBCK URL: {e}")

    for eid, entry in list(active_events_data_store.items()):
        if (current_time_sec - entry.get("alert_arrival_timestamp", 0)) > EVENT_DATA_EXPIRY_SECONDS:
            expired_ids.append(eid)
            continue

        is_past_initial_period = entry.get('is_past_initial_view_period', False)
        has_been_positive = entry.get('has_ever_been_positive_ev', False)

        if is_past_initial_period and not has_been_positive:
            print(f"[Server-ActiveEvents] Hiding event {eid} (past initial view and no +EV).")
            continue

        data_to_send_to_client[eid] = {
            "pinnacle_data_processed": entry.get("pinnacle_processed_data"),
            "alert_trigger_details": entry.get("original_alert_details", {}),
            "betbck_data": entry.get("betbck_comparison_data"),
            "alert_arrival_timestamp": entry.get("alert_arrival_timestamp"),
            "pinnacle_last_update_for_display": entry.get("last_pinnacle_data_update_timestamp"),
            "betbck_main_page_url": betbck_main_url,
            "betbck_search_term_used": entry.get("original_alert_details", {}).get("betbck_search_term_used")
        }
    for eid in expired_ids:
        if eid in active_events_data_store: del active_events_data_store[eid]
    
    return jsonify(data_to_send_to_client)

@app.route('/get_market_details')
def get_market_details():
    try:
        event_id = request.args.get('eventId')
        period_name_req = request.args.get('periodName')
        market_type_req = request.args.get('marketType')
        selection_name_req = request.args.get('selectionName')
        line_display_req = request.args.get('lineDisplay', '')

        if not all([event_id, period_name_req, market_type_req, selection_name_req]):
            return jsonify({"error": "Missing required parameters"}), 400
        if event_id not in active_events_data_store:
            return jsonify({"error": "Event not found or expired"}), 404

        pinnacle_data = active_events_data_store[event_id].get("pinnacle_processed_data", {}).get("data", {})
        if not pinnacle_data or "periods" not in pinnacle_data:
            return jsonify({"error": "Pinnacle data or periods not found"}), 404

        period_num_key = "num_0" if period_name_req.lower() == "match" else "num_1" if period_name_req.lower() == "1st half" else None
        if not period_num_key or period_num_key not in pinnacle_data["periods"]:
            return jsonify({"error": f"Period '{period_name_req}' not found"}), 404
            
        period_data = pinnacle_data["periods"][period_num_key]
        market_to_return = {"status": "Market not found"}

        if market_type_req == "Moneyline":
            ml_data = period_data.get("money_line")
            if ml_data:
                home_team = pinnacle_data.get("home", "").strip()
                sel_key = "home" if selection_name_req.strip() == home_team else "draw" if selection_name_req.lower() == "draw" else "away"
                market_to_return = {"pinnacle_odds_am": ml_data.get(f"american_{sel_key}"), "pinnacle_nvp_am": ml_data.get(f"nvp_american_{sel_key}")}
        elif market_type_req == "Spread":
            spreads = period_data.get("spreads")
            if spreads:
                home_team = pinnacle_data.get("home", "").strip()
                is_home_sel = selection_name_req.strip() == home_team
                target_hdp = ""
                if line_display_req:
                    try:
                        target_hdp = line_display_req if is_home_sel else str(-float(line_display_req))
                        if target_hdp == "-0.0": target_hdp = "0.0"
                    except (ValueError, TypeError): target_hdp = ""
                for hdp, details in spreads.items():
                    if str(details.get("hdp")) == target_hdp or hdp == target_hdp:
                        sel_key = "home" if is_home_sel else "away"
                        market_to_return = {"pinnacle_odds_am": details.get(f"american_{sel_key}"), "pinnacle_nvp_am": details.get(f"nvp_american_{sel_key}")}
                        break
        elif market_type_req == "Total":
            totals = period_data.get("totals")
            if totals:
                details = totals.get(str(line_display_req))
                if details:
                    sel_key = selection_name_req.lower()
                    market_to_return = {"pinnacle_odds_am": details.get(f"american_{sel_key}"), "pinnacle_nvp_am": details.get(f"nvp_american_{sel_key}")}
        
        return jsonify(market_to_return)
    except Exception as e:
        app.logger.error(f"Error in /get_market_details: {e}", exc_info=True)
        return jsonify({"error": "Internal server error processing market details"}), 500

@app.route('/')
@app.route('/odds_table')
def odds_table_page_route(): 
    return render_template('realtime.html')

if __name__ == '__main__':
    print("Starting Python Flask server for POD Automation (v2.3 - Final Stability Fix)...")
    refresher_thread = threading.Thread(target=background_event_refresher, daemon=True)
    refresher_thread.start()
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)