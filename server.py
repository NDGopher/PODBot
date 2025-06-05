from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import time
import math
from datetime import datetime, timedelta
import threading
import traceback

# --- Pinnacle Fetcher ---
try:
    from pinnacle_fetcher import fetch_live_pinnacle_event_odds
except ImportError:
    print("ERROR: pinnacle_fetcher.py not found. Using dummy function.")
    def fetch_live_pinnacle_event_odds(event_id):
        return {"success": False, "error": "pinnacle_fetcher.py missing", "data": None}

# --- Main Logic Integration ---
try:
    from main_logic import process_alert_and_scrape_betbck
    MAIN_LOGIC_AVAILABLE = True
    print("[Server] main_logic.py and process_alert_and_scrape_betbck loaded successfully.")
except ImportError as e:
    print(f"[Server] WARNING: Could not import 'process_alert_and_scrape_betbck' from main_logic.py.")
    print("Full ImportError traceback from server.py trying to import main_logic:")
    traceback.print_exc()
    MAIN_LOGIC_AVAILABLE = False
    def process_alert_and_scrape_betbck(event_id, original_alert_details, processed_pinnacle_data):
        return {"status": "main_logic_unavailable", "message": "main_logic.py or its function not found.", "data": None}
except Exception as e_import_main_logic:
    print(f"[Server] UNEXPECTED ERROR during import of main_logic: {e_import_main_logic}")
    traceback.print_exc()
    MAIN_LOGIC_AVAILABLE = False
    def process_alert_and_scrape_betbck(event_id, original_alert_details, processed_pinnacle_data):
        return {"status": "main_logic_error", "message": "Unexpected error loading main_logic.py.", "data": None}

app = Flask(__name__)
CORS(app)

active_events_data_store = {}
EVENT_DATA_EXPIRY_SECONDS = 5 * 60
BACKGROUND_REFRESH_INTERVAL_SECONDS = 3
# No longer using BETBCK_SCRAPE_COOLDOWN_SECONDS, as we will only try once per eventID if it previously failed.
# We still need to track if an attempt was made to avoid multiple concurrent attempts for the same eventId if alerts are rapid.
betbck_scrape_attempted_for_event_id = set()


# --- NVP and Odds Conversion Utilities (Keep your latest working versions) ---
def decimal_to_american(decimal_odds):
    if decimal_odds is None or not isinstance(decimal_odds, (float, int)): return "N/A"
    if decimal_odds <= 1.0001: return "N/A"
    if decimal_odds >= 2.0: return f"+{int(round((decimal_odds - 1) * 100))}"
    return f"{int(round(-100 / (decimal_odds - 1)))}"

def adjust_power_probabilities(probabilities, tolerance=1e-6, max_iterations=100):
    k = 1.0; valid_probs_for_power = [p for p in probabilities if p is not None and p > 1e-9]
    if not valid_probs_for_power: return [0] * len(probabilities)
    for _ in range(max_iterations):
        current_powered_probs = []; success_pow = True
        try: current_powered_probs = [math.pow(p, k) if p > 0 else 0 for p in valid_probs_for_power]
        except (ValueError, OverflowError): success_pow = False
        if not success_pow: sum_orig = sum(p for p in valid_probs_for_power if p > 0); return [p/sum_orig if sum_orig!=0 and p is not None and p > 0 else 0 for p in valid_probs_for_power]
        sum_powered = sum(current_powered_probs)
        if abs(sum_powered) < 1e-9: break
        overround = sum_powered - 1.0
        if abs(overround) < tolerance: break
        derivative = sum(p_k * math.log(p) if p > 0 else 0 for p,p_k in zip(valid_probs_for_power, current_powered_probs) if p > 0) # Check p > 0 for log
        if abs(derivative) < 1e-9: break
        try: k -= overround / derivative
        except (OverflowError, ZeroDivisionError) : break
    final_powered_probs = []; success_final_pow = True
    try: final_powered_probs = [math.pow(p, k) if p > 0 else 0 for p in valid_probs_for_power]
    except(ValueError, OverflowError): success_final_pow = False
    if not success_final_pow : sum_orig = sum(p for p in valid_probs_for_power if p > 0); return [p/sum_orig if sum_orig!=0 and p is not None and p > 0 else 0 for p in valid_probs_for_power]
    sum_final_powered = sum(final_powered_probs)
    if abs(sum_final_powered) < 1e-9: return [1.0/len(valid_probs_for_power) if valid_probs_for_power else 0]*len(valid_probs_for_power)
    final_true_probs = [p_f / sum_final_powered for p_f in final_powered_probs]
    result_mapped = []; valid_idx_counter = 0
    for original_p_in_list in probabilities:
        if original_p_in_list is not None and original_p_in_list > 1e-9:
            result_mapped.append(final_true_probs[valid_idx_counter] if valid_idx_counter < len(final_true_probs) else 0); valid_idx_counter +=1
        else: result_mapped.append(0) 
    return result_mapped

def calculate_nvp_for_market(odds_list):
    valid_odds_indices = [i for i, odd in enumerate(odds_list) if odd is not None and isinstance(odd, (float,int)) and odd > 1.0001]
    if not valid_odds_indices: return [None] * len(odds_list)
    current_valid_odds = [odds_list[i] for i in valid_odds_indices]
    implied_probs_for_valid_odds = [1.0 / odd for odd in current_valid_odds]
    if not implied_probs_for_valid_odds : return [None] * len(odds_list)
    sum_implied_probs = sum(implied_probs_for_valid_odds)
    if sum_implied_probs <= 1.0001 + 1e-5: nvps_for_valid = [round(odd, 3) for odd in current_valid_odds]
    else:
        true_probs = adjust_power_probabilities(implied_probs_for_valid_odds)
        nvps_for_valid = [round(1.0 / p, 3) if p is not None and p > 1e-9 else None for p in true_probs]
    final_nvp_list = [None] * len(odds_list)
    for i, original_idx in enumerate(valid_odds_indices):
        if i < len(nvps_for_valid): final_nvp_list[original_idx] = nvps_for_valid[i]
    return final_nvp_list

def process_event_odds_for_display(pinnacle_event_json_data): # Keep your latest working version
    # Ensure this correctly iterates .items() for Pinnacle spreads/totals objects
    if not pinnacle_event_json_data or 'data' not in pinnacle_event_json_data: return {"error": "Invalid or missing 'data'", "success": False, "data": {}}
    event_detail = pinnacle_event_json_data['data'];
    if not isinstance(event_detail, dict): return {"error": "'data' field not a dict", "success": False, "data": {}}
    periods = event_detail.get("periods", {})
    if not isinstance(periods, dict): pinnacle_event_json_data.setdefault('data', {}).setdefault('processing_notes', []).append('Periods data missing/invalid'); return pinnacle_event_json_data
    for period_key, period_data in periods.items():
        if not isinstance(period_data, dict): continue
        if period_data.get("money_line") and isinstance(period_data["money_line"], dict):
            ml = period_data["money_line"]; odds = [ml.get("home"), ml.get("draw"), ml.get("away")]; nvps = calculate_nvp_for_market(odds)
            ml["nvp_home"],ml["nvp_draw"],ml["nvp_away"]=(nvps[0] if len(nvps)>0 else None),(nvps[1] if len(nvps)>1 else None),(nvps[2] if len(nvps)>2 else None)
            for k in ["home","draw","away"]: ml[f"american_{k}"]=decimal_to_american(ml.get(k)); ml[f"nvp_american_{k}"]=decimal_to_american(ml.get(f"nvp_{k}"))
        if period_data.get("spreads") and isinstance(period_data["spreads"], dict):
            for _, spread_details in period_data["spreads"].items():
                if isinstance(spread_details, dict):
                    odds=[spread_details.get("home"),spread_details.get("away")]; nvps=calculate_nvp_for_market(odds)
                    spread_details["nvp_home"],spread_details["nvp_away"]=(nvps[0]if len(nvps)>0 else None),(nvps[1]if len(nvps)>1 else None)
                    for k in ["home","away"]: spread_details[f"american_{k}"]=decimal_to_american(spread_details.get(k)); spread_details[f"nvp_american_{k}"]=decimal_to_american(spread_details.get(f"nvp_{k}"))
        if period_data.get("totals") and isinstance(period_data["totals"], dict):
            for _, total_details in period_data["totals"].items():
                if isinstance(total_details, dict):
                    odds=[total_details.get("over"),total_details.get("under")]; nvps=calculate_nvp_for_market(odds)
                    total_details["nvp_over"],total_details["nvp_under"]=(nvps[0]if len(nvps)>0 else None),(nvps[1]if len(nvps)>1 else None)
                    for k in ["over","under"]: total_details[f"american_{k}"]=decimal_to_american(total_details.get(k)); total_details[f"nvp_american_{k}"]=decimal_to_american(total_details.get(f"nvp_{k}"))
    return pinnacle_event_json_data

# --- Background Refresh Thread ---
def background_event_refresher():
    print(f"[BackgroundRefresher] Thread started. Interval: {BACKGROUND_REFRESH_INTERVAL_SECONDS}s")
    while True:
        time.sleep(BACKGROUND_REFRESH_INTERVAL_SECONDS)
        event_ids_to_refresh = list(active_events_data_store.keys())
        if not event_ids_to_refresh: continue
        for event_id_str in event_ids_to_refresh:
            pinnacle_api_result = fetch_live_pinnacle_event_odds(str(event_id_str))
            if pinnacle_api_result and pinnacle_api_result.get("success"):
                live_pinnacle_odds_json = pinnacle_api_result.get("data")
                if live_pinnacle_odds_json:
                    live_pinnacle_odds_processed = process_event_odds_for_display(live_pinnacle_odds_json)
                    existing_entry = active_events_data_store.get(event_id_str, {})
                    active_events_data_store[event_id_str] = {
                        "alert_arrival_timestamp": existing_entry.get("alert_arrival_timestamp", time.time()), # Preserve original
                        "last_pinnacle_data_update_timestamp": time.time(),
                        "pinnacle_processed_data": live_pinnacle_odds_processed,
                        "original_alert_details": existing_entry.get("original_alert_details", {}),
                        "betbck_comparison_data": existing_entry.get("betbck_comparison_data", None)
                    }

@app.route('/pod_alert', methods=['POST'])
def handle_pod_alert():
    try:
        payload = request.json; event_id = payload.get("eventId"); original_alert_details = payload
        if not event_id: return jsonify({"status": "error", "message": "Missing eventId"}), 400
        event_id_str = str(event_id); now = time.time()
        print(f"\n[Server-PodAlert] Received alert for Event ID: {event_id_str} ({original_alert_details.get('homeTeam','?')})")

        pinnacle_api_result = fetch_live_pinnacle_event_odds(event_id_str)
        live_pinnacle_odds_processed = {"error": "Pinnacle fetch failed initially", "success": False, "data": {}}
        if pinnacle_api_result and pinnacle_api_result.get("success") and pinnacle_api_result.get("data"):
            live_pinnacle_odds_processed = process_event_odds_for_display(pinnacle_api_result.get("data"))
        elif pinnacle_api_result: live_pinnacle_odds_processed["error"] = pinnacle_api_result.get("error", "Pinnacle fetch error")
        
        existing_entry = active_events_data_store.get(event_id_str)
        alert_arrival_ts_to_store = existing_entry.get("alert_arrival_timestamp") if existing_entry else now
        betbck_data_from_store = existing_entry.get("betbck_comparison_data") if existing_entry else None

        current_betbck_status_in_store = None
        if betbck_data_from_store and isinstance(betbck_data_from_store, dict):
            current_betbck_status_in_store = betbck_data_from_store.get("status")

        active_events_data_store[event_id_str] = {
            "alert_arrival_timestamp": alert_arrival_ts_to_store,
            "last_pinnacle_data_update_timestamp": now,
            "pinnacle_processed_data": live_pinnacle_odds_processed,
            "original_alert_details": original_alert_details,
            "betbck_comparison_data": betbck_data_from_store # Carry over, will be updated if scrape happens
        }

        # --- Conditional BetBCK Scraping: Only if not successfully scraped before OR if it previously failed (no cooldown on failure) ---
        should_attempt_betbck_scrape = True
        if current_betbck_status_in_store == "success":
            print(f"[Server-PodAlert] BetBCK data already successfully fetched for {event_id_str}. Skipping new scrape.")
            should_attempt_betbck_scrape = False
        elif event_id_str in betbck_scrape_attempted_for_event_id and current_betbck_status_in_store != "success":
            # If it was attempted and failed, we still allow a new attempt on a *new alert* for that eventID.
            # The cooldown in previous versions was preventing this. This version allows a retry on each new alert if prior failed.
            # If you want a cooldown even on failure, re-add the timestamp check here.
            print(f"[Server-PodAlert] Prior BetBCK attempt for {event_id_str} failed or was unavailable. Allowing new attempt.")
        
        # To prevent rapid re-scrapes if alerts come in bunches for the *same game before first scrape finishes*:
        # This is a simpler in-flight check.
        # For a more robust solution against many identical alerts, the cooldown logic using betbck_last_attempt_timestamp was better.
        # For now, the "only if current_betbck_status_in_store != 'success'" is the main gate.

        if MAIN_LOGIC_AVAILABLE and should_attempt_betbck_scrape:
            print(f"[Server-PodAlert] Initiating BetBCK processing for event {event_id_str}...")
            betbck_scrape_attempted_for_event_id.add(event_id_str) # Mark that an attempt is being made for this session

            betbck_result = process_alert_and_scrape_betbck(event_id_str, original_alert_details, live_pinnacle_odds_processed)
            
            if event_id_str in active_events_data_store: # Update with new result
                 active_events_data_store[event_id_str]["betbck_comparison_data"] = betbck_result
            
            status_msg = betbck_result.get('status','N/A') if isinstance(betbck_result, dict) else "Unknown"
            print(f"[Server-PodAlert] main_logic BetBCK result status for {event_id_str}: {status_msg}")
            
            # If scrape failed, we might want to remove from betbck_scrape_attempted_for_event_id 
            # to allow the *very next* alert for this eventID to try again,
            # instead of waiting for server restart or explicit clearing.
            # This makes it retry on every new alert if the previous was a failure.
            if status_msg != "success" and event_id_str in betbck_scrape_attempted_for_event_id:
                 betbck_scrape_attempted_for_event_id.remove(event_id_str)

        elif not MAIN_LOGIC_AVAILABLE:
             print(f"[Server-PodAlert] Main logic unavailable, BetBCK call skipped for {event_id_str}.")
        
        return jsonify({"status": "success", "message": f"Alert for {event_id_str} processed."}), 200
    except Exception as e:
        print(f"[Server-PodAlert] CRITICAL Error in /pod_alert: {e}"); traceback.print_exc()
        return jsonify({"status": "error", "message": f"Internal server error: {str(e)}"}), 500

@app.route('/get_active_events_data', methods=['GET'])
def get_active_events_data():
    current_time_sec = time.time(); data_to_send_to_client = {}; expired_ids = []
    for eid, entry in list(active_events_data_store.items()):
        if (current_time_sec - entry.get("alert_arrival_timestamp", current_time_sec + EVENT_DATA_EXPIRY_SECONDS + 1)) > EVENT_DATA_EXPIRY_SECONDS:
            expired_ids.append(eid)
        else:
            data_to_send_to_client[eid] = {
                "pinnacle_data_processed": entry.get("pinnacle_processed_data"),
                "alert_trigger_details": entry.get("original_alert_details", {}),
                "betbck_data": entry.get("betbck_comparison_data", None), # This will be passed to JS
                "alert_arrival_timestamp": entry.get("alert_arrival_timestamp"),
                "pinnacle_last_update_for_display": entry.get("last_pinnacle_data_update_timestamp")
            }
    for eid in expired_ids:
        if eid in active_events_data_store: del active_events_data_store[eid]
        if eid in betbck_scrape_attempted_for_event_id: betbck_scrape_attempted_for_event_id.remove(eid) # Clean up tracker
        print(f"[Server-ActiveEvents] Expired eventId {eid}.")
    return jsonify(data_to_send_to_client)

@app.route('/odds_table')
def odds_table_page_route(): return render_template('realtime.html')

if __name__ == '__main__':
    print("Starting Python Flask server for POD Automation (v1.4 - Cooldown Refined)...")
    refresher_thread = threading.Thread(target=background_event_refresher, daemon=True); refresher_thread.start()
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)