from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import json
import time
import math
from datetime import datetime, timedelta
import threading
import traceback
import os # Added for path joining

# --- MODIFICATION: Define SCRIPT_DIR and CONFIG_FILE_PATH ---
# Ensure this points to your config.json file correctly
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(SCRIPT_DIR, 'config.json')
# --- END MODIFICATION ---

# --- Pinnacle Fetcher ---
try:
    from pinnacle_fetcher import fetch_live_pinnacle_event_odds
except ImportError:
    print("ERROR: pinnacle_fetcher.py not found. Using dummy function.")
    def fetch_live_pinnacle_event_odds(event_id):
        return {"success": False, "error": "pinnacle_fetcher.py missing", "data": None}

# --- Main Logic Integration ---
try:
    from main_logic import process_alert_and_scrape_betbck # Assuming main_logic.py is in the same directory
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
betbck_scrape_attempted_for_event_id = set()


# --- NVP and Odds Conversion Utilities (Keep your latest working versions) ---
def decimal_to_american(decimal_odds):
    if decimal_odds is None or not isinstance(decimal_odds, (float, int)): return "N/A"
    if decimal_odds <= 1.0001: return "N/A"
    if decimal_odds >= 2.0: return f"+{int(round((decimal_odds - 1) * 100))}"
    return f"{int(round(-100 / (decimal_odds - 1)))}"

def adjust_power_probabilities(probabilities, tolerance=1e-6, max_iterations=100):
    k = 1.0; valid_probs_for_power = [p for p in probabilities if p is not None and p > 1e-9]
    if not valid_probs_for_power: return [0] * len(probabilities) # Return list of zeros matching original length
    
    # Handle case where only one valid probability exists after filtering
    if len(valid_probs_for_power) == 1:
        # Map this single '1.0' probability back to its original position
        result_mapped_single = []
        valid_idx_counter_single = 0
        for original_p_in_list_single in probabilities:
            if original_p_in_list_single is not None and original_p_in_list_single > 1e-9:
                result_mapped_single.append(1.0 if valid_idx_counter_single == 0 else 0) # Should only be one
                valid_idx_counter_single += 1
            else:
                result_mapped_single.append(0)
        return result_mapped_single

    for _ in range(max_iterations):
        current_powered_probs = []; success_pow = True
        try: current_powered_probs = [math.pow(p, k) if p > 0 else 0 for p in valid_probs_for_power]
        except (ValueError, OverflowError): success_pow = False
        if not success_pow: 
            sum_orig = sum(p for p in valid_probs_for_power if p is not None and p > 0) # Ensure p is not None
            # Map back the normalized original probabilities if power calculation fails
            normalized_originals = [p/sum_orig if sum_orig!=0 and p is not None and p > 0 else 0 for p in valid_probs_for_power]
            result_mapped_fail = []
            valid_idx_counter_f = 0
            for original_p_in_list_f in probabilities:
                if original_p_in_list_f is not None and original_p_in_list_f > 1e-9:
                    result_mapped_fail.append(normalized_originals[valid_idx_counter_f] if valid_idx_counter_f < len(normalized_originals) else 0)
                    valid_idx_counter_f +=1
                else: result_mapped_fail.append(0)
            return result_mapped_fail

        sum_powered = sum(current_powered_probs)
        if abs(sum_powered) < 1e-9: break 
        overround = sum_powered - 1.0
        if abs(overround) < tolerance: break
        
        derivative_terms = []
        for p_val, p_k_val in zip(valid_probs_for_power, current_powered_probs):
             if p_val > 0: # log(0) is undefined
                 try:
                     derivative_terms.append(p_k_val * math.log(p_val))
                 except ValueError: # Should not happen if p_val > 0
                     derivative_terms.append(0)
             else:
                 derivative_terms.append(0)
        derivative = sum(derivative_terms)

        if abs(derivative) < 1e-9: break
        try: k -= overround / derivative
        except (OverflowError, ZeroDivisionError) : break # Break on numerical instability

    final_powered_probs = []; success_final_pow = True
    try: final_powered_probs = [math.pow(p, k) if p > 0 else 0 for p in valid_probs_for_power]
    except(ValueError, OverflowError): success_final_pow = False
    
    if not success_final_pow : 
        sum_orig_final = sum(p for p in valid_probs_for_power if p is not None and p > 0)
        normalized_originals_final = [p/sum_orig_final if sum_orig_final!=0 and p is not None and p > 0 else 0 for p in valid_probs_for_power]
        result_mapped_ff = []
        valid_idx_counter_ff = 0
        for original_p_in_list_ff in probabilities:
            if original_p_in_list_ff is not None and original_p_in_list_ff > 1e-9:
                result_mapped_ff.append(normalized_originals_final[valid_idx_counter_ff] if valid_idx_counter_ff < len(normalized_originals_final) else 0)
                valid_idx_counter_ff +=1
            else: result_mapped_ff.append(0)
        return result_mapped_ff

    sum_final_powered = sum(final_powered_probs)
    if abs(sum_final_powered) < 1e-9: 
        # Fallback: Distribute probability equally among valid original inputs if sum is zero
        num_valid_probs = len(valid_probs_for_power)
        equal_prob = 1.0 / num_valid_probs if num_valid_probs > 0 else 0
        final_true_probs = [equal_prob] * num_valid_probs
    else:
        final_true_probs = [p_f / sum_final_powered for p_f in final_powered_probs]
    
    result_mapped = []; valid_idx_counter = 0
    for original_p_in_list in probabilities:
        if original_p_in_list is not None and original_p_in_list > 1e-9:
            result_mapped.append(final_true_probs[valid_idx_counter] if valid_idx_counter < len(final_true_probs) else 0)
            valid_idx_counter +=1
        else: result_mapped.append(0) 
    return result_mapped


def calculate_nvp_for_market(odds_list):
    valid_odds_indices = [i for i, odd in enumerate(odds_list) if odd is not None and isinstance(odd, (float,int)) and odd > 1.0001]
    if not valid_odds_indices: return [None] * len(odds_list)
    
    current_valid_odds = [odds_list[i] for i in valid_odds_indices]
    implied_probs_for_valid_odds = []
    for odd_val in current_valid_odds:
        if odd_val == 0: # Should not happen with odd > 1.0001 filter, but defensive
             implied_probs_for_valid_odds.append(0) # Or handle as error/None
        else:
             implied_probs_for_valid_odds.append(1.0 / odd_val)

    if not implied_probs_for_valid_odds : return [None] * len(odds_list)
    
    sum_implied_probs = sum(p for p in implied_probs_for_valid_odds if p is not None) # Ensure None is not summed

    if sum_implied_probs <= 1.0001 + 1e-5: # If sum is less than or equal to 1 (no vig or tiny negative vig)
        nvps_for_valid = [round(odd, 3) for odd in current_valid_odds]
    else:
        # Create a list of implied probabilities corresponding to the original odds_list structure for adjust_power_probabilities
        full_implied_probs_list = [None] * len(odds_list)
        for i, original_idx in enumerate(valid_odds_indices):
            if i < len(implied_probs_for_valid_odds):
                 full_implied_probs_list[original_idx] = implied_probs_for_valid_odds[i]
        
        # Pass the structured list of implied probabilities
        true_probs_full_structure = adjust_power_probabilities(full_implied_probs_list)

        # Extract the true probabilities for the valid odds positions
        true_probs_for_valid_positions = [true_probs_full_structure[i] for i in valid_odds_indices if true_probs_full_structure[i] is not None and true_probs_full_structure[i] > 1e-9]

        nvps_for_valid = [round(1.0 / p, 3) if p is not None and p > 1e-9 else None for p in true_probs_for_valid_positions]

    final_nvp_list = [None] * len(odds_list)
    processed_nvp_idx = 0
    for i, original_idx in enumerate(valid_odds_indices):
        # Ensure we only assign if there's a corresponding NVP from the valid calculations
        if processed_nvp_idx < len(nvps_for_valid): 
            final_nvp_list[original_idx] = nvps_for_valid[processed_nvp_idx]
            processed_nvp_idx +=1
        # else: final_nvp_list[original_idx] remains None, which is correct if NVP calc failed for it
    return final_nvp_list


def process_event_odds_for_display(pinnacle_event_json_data): 
    if not pinnacle_event_json_data or 'data' not in pinnacle_event_json_data: return {"error": "Invalid or missing 'data'", "success": False, "data": {}}
    event_detail = pinnacle_event_json_data['data']
    if not isinstance(event_detail, dict): return {"error": "'data' field not a dict", "success": False, "data": {}}
    
    periods = event_detail.get("periods", {})
    if not isinstance(periods, dict): 
        # If periods is missing or not a dict, still return the original structure but note it.
        pinnacle_event_json_data.setdefault('data', {}).setdefault('processing_notes', []).append('Periods data missing or not a dictionary.')
        return pinnacle_event_json_data # Return the original (or slightly modified) structure

    for period_key, period_data in periods.items():
        if not isinstance(period_data, dict): continue

        if period_data.get("money_line") and isinstance(period_data["money_line"], dict):
            ml = period_data["money_line"]
            odds_dec = [ml.get("home"), ml.get("draw"), ml.get("away")]
            nvps_dec = calculate_nvp_for_market(odds_dec)
            ml["nvp_home"] = nvps_dec[0] if len(nvps_dec) > 0 else None
            ml["nvp_draw"] = nvps_dec[1] if len(nvps_dec) > 1 else None
            ml["nvp_away"] = nvps_dec[2] if len(nvps_dec) > 2 else None
            for k_ml in ["home", "draw", "away"]:
                ml[f"american_{k_ml}"] = decimal_to_american(ml.get(k_ml))
                ml[f"nvp_american_{k_ml}"] = decimal_to_american(ml.get(f"nvp_{k_ml}"))

        if period_data.get("spreads") and isinstance(period_data["spreads"], dict):
            for hdp_key, spread_details in period_data["spreads"].items(): # hdp_key is the actual hdp like "1.5", "-2.0"
                if isinstance(spread_details, dict):
                    # Add hdp to spread_details if not present, from the key
                    if "hdp" not in spread_details and hdp_key is not None:
                        try: spread_details["hdp"] = float(hdp_key)
                        except ValueError: pass # If key isn't a float, skip adding hdp from key

                    odds_dec_spread = [spread_details.get("home"), spread_details.get("away")]
                    nvps_dec_spread = calculate_nvp_for_market(odds_dec_spread)
                    spread_details["nvp_home"] = nvps_dec_spread[0] if len(nvps_dec_spread) > 0 else None
                    spread_details["nvp_away"] = nvps_dec_spread[1] if len(nvps_dec_spread) > 1 else None
                    for k_spread in ["home", "away"]:
                        spread_details[f"american_{k_spread}"] = decimal_to_american(spread_details.get(k_spread))
                        spread_details[f"nvp_american_{k_spread}"] = decimal_to_american(spread_details.get(f"nvp_{k_spread}"))
        
        if period_data.get("totals") and isinstance(period_data["totals"], dict):
            for points_key, total_details in period_data["totals"].items(): # points_key is the actual points like "2.5", "180.0"
                if isinstance(total_details, dict):
                    # Add points to total_details if not present, from the key
                    if "points" not in total_details and points_key is not None:
                        try: total_details["points"] = float(points_key)
                        except ValueError: pass

                    odds_dec_total = [total_details.get("over"), total_details.get("under")]
                    nvps_dec_total = calculate_nvp_for_market(odds_dec_total)
                    total_details["nvp_over"] = nvps_dec_total[0] if len(nvps_dec_total) > 0 else None
                    total_details["nvp_under"] = nvps_dec_total[1] if len(nvps_dec_total) > 1 else None
                    for k_total in ["over", "under"]:
                        total_details[f"american_{k_total}"] = decimal_to_american(total_details.get(k_total))
                        total_details[f"nvp_american_{k_total}"] = decimal_to_american(total_details.get(f"nvp_{k_total}"))
    return pinnacle_event_json_data


# --- Background Refresh Thread ---
def background_event_refresher():
    print(f"[BackgroundRefresher] Thread started. Interval: {BACKGROUND_REFRESH_INTERVAL_SECONDS}s")
    while True:
        time.sleep(BACKGROUND_REFRESH_INTERVAL_SECONDS)
        event_ids_to_refresh = list(active_events_data_store.keys())
        if not event_ids_to_refresh: continue
        
        for event_id_str_refresh in event_ids_to_refresh:
            try:
                print(f"[BackgroundRefresher] Refreshing Pinnacle data for event: {event_id_str_refresh}")
                pinnacle_api_result = fetch_live_pinnacle_event_odds(str(event_id_str_refresh)) # Ensure it's a string
                
                if pinnacle_api_result and pinnacle_api_result.get("success"):
                    live_pinnacle_odds_json = pinnacle_api_result.get("data")
                    if live_pinnacle_odds_json:
                        live_pinnacle_odds_processed = process_event_odds_for_display(live_pinnacle_odds_json)
                        
                        # Safely update existing entry, preserving crucial fields
                        if event_id_str_refresh in active_events_data_store: # Check if event still exists
                            existing_entry = active_events_data_store[event_id_str_refresh]
                            active_events_data_store[event_id_str_refresh] = {
                                "alert_arrival_timestamp": existing_entry.get("alert_arrival_timestamp", time.time()), # Preserve original if exists
                                "last_pinnacle_data_update_timestamp": time.time(), # New update time
                                "pinnacle_processed_data": live_pinnacle_odds_processed, # New Pinnacle data
                                "original_alert_details": existing_entry.get("original_alert_details", {}), # Preserve
                                "betbck_comparison_data": existing_entry.get("betbck_comparison_data", None) # Preserve
                            }
                            print(f"[BackgroundRefresher] Successfully updated Pinnacle data for event: {event_id_str_refresh}")
                        else:
                            print(f"[BackgroundRefresher] Event {event_id_str_refresh} was removed during refresh process. Skipping update.")
                    else:
                        print(f"[BackgroundRefresher] No data in Pinnacle API result for {event_id_str_refresh}.")
                else:
                    error_msg = pinnacle_api_result.get("error", "Unknown error") if pinnacle_api_result else "Empty API result"
                    print(f"[BackgroundRefresher] Pinnacle fetch FAILED for {event_id_str_refresh}. Error: {error_msg}")
                    # Optionally, update existing_entry with error status for pinnacle if needed by frontend
                    if event_id_str_refresh in active_events_data_store:
                         active_events_data_store[event_id_str_refresh]["last_pinnacle_data_update_timestamp"] = time.time()
                         active_events_data_store[event_id_str_refresh]["pinnacle_processed_data"] = {
                             "success": False, 
                             "error": f"Background refresh failed: {error_msg}", 
                             "data": active_events_data_store[event_id_str_refresh].get("pinnacle_processed_data",{}).get("data") # Keep old data if any
                         }


            except Exception as e_bg_refresh:
                print(f"[BackgroundRefresher] CRITICAL Error during refresh of event {event_id_str_refresh}: {e_bg_refresh}")
                traceback.print_exc()


@app.route('/pod_alert', methods=['POST'])
def handle_pod_alert():
    try:
        payload = request.json
        event_id = payload.get("eventId")
        original_alert_details = payload # The whole payload is the original_alert_details

        if not event_id: 
            return jsonify({"status": "error", "message": "Missing eventId"}), 400
        
        event_id_str = str(event_id)
        now = time.time()
        print(f"\n[Server-PodAlert] Received alert for Event ID: {event_id_str} ({original_alert_details.get('homeTeam','?')})")

        # Fetch Pinnacle data immediately for a new alert
        pinnacle_api_result = fetch_live_pinnacle_event_odds(event_id_str)
        live_pinnacle_odds_processed = {"error": "Pinnacle fetch failed initially", "success": False, "data": {}}
        
        if pinnacle_api_result and pinnacle_api_result.get("success") and pinnacle_api_result.get("data"):
            live_pinnacle_odds_processed = process_event_odds_for_display(pinnacle_api_result.get("data"))
        elif pinnacle_api_result: # Fetch attempt was made but failed
            live_pinnacle_odds_processed["error"] = pinnacle_api_result.get("error", "Pinnacle fetch error during alert processing")
            live_pinnacle_odds_processed["data"] = pinnacle_api_result.get("data") # Keep raw data if any, even on error

        existing_entry = active_events_data_store.get(event_id_str)
        alert_arrival_ts_to_store = now # For a new alert, always use current time as arrival
        
        # Preserve BetBCK data if this event_id was already known (e.g., from a previous alert for the same game)
        betbck_data_from_store = existing_entry.get("betbck_comparison_data") if existing_entry else None
        
        active_events_data_store[event_id_str] = {
            "alert_arrival_timestamp": alert_arrival_ts_to_store,
            "last_pinnacle_data_update_timestamp": now, # Timestamp of this Pinnacle data fetch
            "pinnacle_processed_data": live_pinnacle_odds_processed,
            "original_alert_details": original_alert_details, # This now includes betbck_search_term_used if main_logic added it
            "betbck_comparison_data": betbck_data_from_store 
        }
        
        # --- BetBCK Scraping Logic ---
        # Decide if BetBCK scrape is needed.
        # Only scrape if:
        # 1. MAIN_LOGIC_AVAILABLE is True.
        # 2. This event_id hasn't had a SUCCESSFUL BetBCK scrape yet OR
        #    if the previous attempt for this event_id was NOT successful (e.g. error, no data).
        
        should_attempt_betbck_scrape = False
        if MAIN_LOGIC_AVAILABLE:
            current_betbck_status_in_store = None
            if betbck_data_from_store and isinstance(betbck_data_from_store, dict):
                current_betbck_status_in_store = betbck_data_from_store.get("status")

            if current_betbck_status_in_store == "success":
                print(f"[Server-PodAlert] BetBCK data already successfully fetched for {event_id_str}. Skipping new scrape.")
            else: # Not successful before, or never tried
                if current_betbck_status_in_store: # Means it was tried but not 'success'
                     print(f"[Server-PodAlert] Prior BetBCK attempt for {event_id_str} was '{current_betbck_status_in_store}'. Allowing new attempt.")
                else: # Never tried
                     print(f"[Server-PodAlert] No prior BetBCK attempt for {event_id_str}. Initiating scrape.")
                should_attempt_betbck_scrape = True
                # Simple way to prevent multiple concurrent scrapes for the same ID if alerts are too rapid:
                # Mark as attempted *before* calling. If it fails, it will be cleared below to allow next alert to try.
                if event_id_str not in betbck_scrape_attempted_for_event_id :
                    betbck_scrape_attempted_for_event_id.add(event_id_str)
                else: # Already marked as attempting, likely another alert came in while first was running.
                    print(f"[Server-PodAlert] BetBCK scrape for {event_id_str} already in progress by another thread/alert. Skipping this one.")
                    should_attempt_betbck_scrape = False # Prevent re-entry for this specific call


        if should_attempt_betbck_scrape: # Guarded by MAIN_LOGIC_AVAILABLE already
            print(f"[Server-PodAlert] Initiating BetBCK processing for event {event_id_str}...")
            # Call main_logic, which now modifies original_alert_details in-place
            betbck_result = process_alert_and_scrape_betbck(
                event_id_str, 
                active_events_data_store[event_id_str]["original_alert_details"], # Pass the dict from store
                live_pinnacle_odds_processed
            )
            
            if event_id_str in active_events_data_store: # Update with new result
                 active_events_data_store[event_id_str]["betbck_comparison_data"] = betbck_result
            
            status_msg = betbck_result.get('status','N/A') if isinstance(betbck_result, dict) else "Unknown"
            print(f"[Server-PodAlert] main_logic BetBCK result status for {event_id_str}: {status_msg}")
            
            # If scrape was not successful, remove from the "attempted" set so the *next* alert for this event can try again.
            # If it was successful, it stays in the set (implicitly, because we don't remove it), and the logic above
            # will prevent re-scraping for "success" status.
            if status_msg != "success":
                if event_id_str in betbck_scrape_attempted_for_event_id:
                    betbck_scrape_attempted_for_event_id.remove(event_id_str)
                    print(f"[Server-PodAlert] BetBCK scrape for {event_id_str} was not successful. Cleared from attempt set for future retries.")
            else: # Successful
                # If you want to keep it in the set to prevent any further scrapes for this ID in this session:
                # betbck_scrape_attempted_for_event_id.add(event_id_str) # (Redundant if logic above adds it)
                print(f"[Server-PodAlert] BetBCK scrape for {event_id_str} was successful. Future alerts for this ID in this session might not re-scrape BetBCK.")


        elif not MAIN_LOGIC_AVAILABLE:
             print(f"[Server-PodAlert] Main logic unavailable, BetBCK call skipped for {event_id_str}.")
        
        return jsonify({"status": "success", "message": f"Alert for {event_id_str} processed."}), 200
    except Exception as e:
        print(f"[Server-PodAlert] CRITICAL Error in /pod_alert: {e}"); traceback.print_exc()
        return jsonify({"status": "error", "message": f"Internal server error: {str(e)}"}), 500

@app.route('/get_active_events_data', methods=['GET'])
def get_active_events_data():
    current_time_sec = time.time()
    data_to_send_to_client = {}
    expired_ids = []

    # --- MODIFICATION: Load BetBCK main page URL from config ---
    betbck_main_url = None
    try:
        with open(CONFIG_FILE_PATH, 'r') as f:
            config_data = json.load(f) # Renamed to avoid conflict if 'config' is used elsewhere
        betbck_main_url = config_data.get('betbck', {}).get('main_page_url_after_login')
    except FileNotFoundError:
        print(f"[Server-ActiveEvents] ERROR: config.json not found at {CONFIG_FILE_PATH}")
    except Exception as e_cfg_read:
        print(f"[Server-ActiveEvents] Error reading betbck_main_url from config: {e_cfg_read}")
    # --- END MODIFICATION ---

    for eid_str, entry_data in list(active_events_data_store.items()): # Use more descriptive names
        # Check for expiry based on alert_arrival_timestamp
        if (current_time_sec - entry_data.get("alert_arrival_timestamp", current_time_sec + EVENT_DATA_EXPIRY_SECONDS + 1)) > EVENT_DATA_EXPIRY_SECONDS:
            expired_ids.append(eid_str)
        else:
            original_alert_details_entry = entry_data.get("original_alert_details", {})
            # --- MODIFICATION: Retrieve betbck_search_term_used ---
            betbck_search_term_from_entry = original_alert_details_entry.get("betbck_search_term_used")
            # --- END MODIFICATION ---

            data_to_send_to_client[eid_str] = {
                "pinnacle_data_processed": entry_data.get("pinnacle_processed_data"),
                "alert_trigger_details": original_alert_details_entry,
                "betbck_data": entry_data.get("betbck_comparison_data", None), 
                "alert_arrival_timestamp": entry_data.get("alert_arrival_timestamp"),
                "pinnacle_last_update_for_display": entry_data.get("last_pinnacle_data_update_timestamp"),
                # --- MODIFICATION: Add to client data ---
                "betbck_main_page_url": betbck_main_url,
                "betbck_search_term_used": betbck_search_term_from_entry
                # --- END MODIFICATION ---
            }

    for expired_event_id in expired_ids:
        if expired_event_id in active_events_data_store: 
            del active_events_data_store[expired_event_id]
        if expired_event_id in betbck_scrape_attempted_for_event_id: # Clean up tracker
            betbck_scrape_attempted_for_event_id.remove(expired_event_id)
        print(f"[Server-ActiveEvents] Expired and removed eventId {expired_event_id}.")
    
    return jsonify(data_to_send_to_client)

@app.route('/') # Route for the main page
@app.route('/odds_table')
def odds_table_page_route(): 
    return render_template('realtime.html')

if __name__ == '__main__':
    print("Starting Python Flask server for POD Automation (v1.5 - EV Pop-up Support)...")
    refresher_thread = threading.Thread(target=background_event_refresher, daemon=True)
    refresher_thread.start()
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False)