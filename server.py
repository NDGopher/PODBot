from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import time
import threading
import traceback

from utils import process_event_odds_for_display
from pinnacle_fetcher import fetch_live_pinnacle_event_odds
from main_logic import process_alert_and_scrape_betbck, clean_pod_team_name_for_search

app = Flask(__name__)
CORS(app, resources={r"/get_active_events_data": {"origins": "*"}})
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0

active_events_data_store = {}
EVENT_DATA_EXPIRY_SECONDS = 300
BACKGROUND_REFRESH_INTERVAL_SECONDS = 3

def background_event_refresher():
    while True:
        try:
            time.sleep(BACKGROUND_REFRESH_INTERVAL_SECONDS)
            current_time = time.time()
            for event_id, event_data in list(active_events_data_store.items()):
                if (current_time - event_data.get("alert_arrival_timestamp", 0)) > EVENT_DATA_EXPIRY_SECONDS:
                    del active_events_data_store[event_id]
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

        if event_id_str not in active_events_data_store:
            print(f"[Server-PodAlert] New event {event_id_str}. Initiating scrape.")
            betbck_result = process_alert_and_scrape_betbck(event_id_str, payload, live_pinnacle_odds_processed)

            if not (betbck_result and betbck_result.get("status") == "success"):
                fail_reason = betbck_result.get("message", "Scraper returned None")
                print(f"[Server-PodAlert] Scrape failed. Dropping alert. Reason: {fail_reason}")
                return jsonify({"status": "error", "message": f"Scrape failed: {fail_reason}"}), 200

            print(f"[Server-PodAlert] Scrape successful. Storing event {event_id_str} for display.")
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
                "cleaned_away_team": pod_away_clean
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
        # Filter out historical data
        if 'periods' in pinnacle_data:
            for period in pinnacle_data['periods'].values():
                if 'spreads' in period:
                    period['spreads'] = {k: v for k, v in period['spreads'].items() if not isinstance(v, list)}
                if 'totals' in period:
                    period['totals'] = {k: v for k, v in period['totals'].items() if not isinstance(v, list)}
                if 'team_total' in period:
                    period['team_total'] = {k: v for k, v in period['team_total'].items() if not isinstance(v, list)}
        pinnacle_periods = pinnacle_data.get("periods", {})
        pin_full_game = pinnacle_periods.get("num_0", {})
        pin_1h = pinnacle_periods.get("num_1")
        if pin_1h is None:
            print(f"[GetActiveEvents] No 1H data for Event ID: {eid}, using empty dict")
            pin_1h = {}
        data_to_send[eid] = {
            "title": f"{entry['cleaned_home_team']} vs {entry['cleaned_away_team']}",
            "meta_info": f"{entry['league_name']} | Starts: {entry['start_time']}",
            "last_update": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(entry["last_pinnacle_data_update_timestamp"])),
            "alert_description": entry['original_alert_details'].get("betDescription", "POD Alert Processed"),
            "alert_meta": f"(Alert: {entry['old_odds']} → {entry['new_odds']}, NVP: {entry['no_vig']})",
            "betbck_status": f"Data Fetched: {bet_data.get('pod_home_team', 'N/A')} vs {bet_data.get('pod_away_team', 'N/A')}" if entry["betbck_data"].get("status") == "success" else entry["betbck_data"].get("message", "Odds check pending..."),
            "markets": [
                {"market": "ML", "selection": "Home", "line": "", "pinnacle_nvp": pin_full_game.get("money_line", {}).get("nvp_american_home"), "betbck_odds": bet_data.get("home_moneyline_american"), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "ML" and b["selection"] == "Home"), "N/A")},
                {"market": "ML", "selection": "Away", "line": "", "pinnacle_nvp": pin_full_game.get("money_line", {}).get("nvp_american_away"), "betbck_odds": bet_data.get("away_moneyline_american"), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "ML" and b["selection"] == "Away"), "N/A")},
                {"market": "ML", "selection": "Draw", "line": "", "pinnacle_nvp": pin_full_game.get("money_line", {}).get("nvp_american_draw"), "betbck_odds": bet_data.get("draw_moneyline_american"), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "ML" and b["selection"] == "Draw"), "N/A")},
                {"market": "ML 1H", "selection": "Home", "line": "", "pinnacle_nvp": pin_1h.get("money_line", {}).get("nvp_american_home"), "betbck_odds": bet_data.get("home_moneyline_american_1h"), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "ML 1H" and b["selection"] == "Home"), "N/A")},
                {"market": "ML 1H", "selection": "Away", "line": "", "pinnacle_nvp": pin_1h.get("money_line", {}).get("nvp_american_away"), "betbck_odds": bet_data.get("away_moneyline_american_1h"), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "ML 1H" and b["selection"] == "Away"), "N/A")},
                {"market": "ML 1H", "selection": "Draw", "line": "", "pinnacle_nvp": pin_1h.get("money_line", {}).get("nvp_american_draw"), "betbck_odds": bet_data.get("draw_moneyline_american_1h"), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "ML 1H" and b["selection"] == "Draw"), "N/A")},
                {"market": "Spread", "selection": "Home", "line": next((str(s.get("hdp", "")) for s in pin_full_game.get("spreads", {}).values()), ""), "pinnacle_nvp": next((s.get("nvp_american_home", None) for s in pin_full_game.get("spreads", {}).values()), None), "betbck_odds": next((s.get("odds", None) for s in bet_data.get("home_spreads", []) if str(s.get("line", s.get("hdp", ""))) == next((str(s2.get("hdp", "")) for s2 in pin_full_game.get("spreads", {}).values()), "")), None), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "Spread" and b["selection"] == "Home"), "N/A")},
                {"market": "Spread", "selection": "Away", "line": next((str(s.get("hdp", "")) for s in pin_full_game.get("spreads", {}).values()), ""), "pinnacle_nvp": next((s.get("nvp_american_away", None) for s in pin_full_game.get("spreads", {}).values()), None), "betbck_odds": next((s.get("odds", None) for s in bet_data.get("away_spreads", []) if str(s.get("line", s.get("hdp", ""))) == next((str(-s2.get("hdp", "")) for s2 in pin_full_game.get("spreads", {}).values()), "")), None), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "Spread" and b["selection"] == "Away"), "N/A")},
                {"market": "Spread 1H", "selection": "Home", "line": next((str(s.get("hdp", "")) for s in pin_1h.get("spreads", {}).values()), ""), "pinnacle_nvp": next((s.get("nvp_american_home", None) for s in pin_1h.get("spreads", {}).values()), None), "betbck_odds": next((s.get("odds", None) for s in bet_data.get("home_spreads_1h", []) if str(s.get("line", s.get("hdp", ""))) == next((str(s2.get("hdp", "")) for s2 in pin_1h.get("spreads", {}).values()), "")), None), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "Spread 1H" and b["selection"] == "Home"), "N/A")},
                {"market": "Spread 1H", "selection": "Away", "line": next((str(s.get("hdp", "")) for s in pin_1h.get("spreads", {}).values()), ""), "pinnacle_nvp": next((s.get("nvp_american_away", None) for s in pin_1h.get("spreads", {}).values()), None), "betbck_odds": next((s.get("odds", None) for s in bet_data.get("away_spreads_1h", []) if str(s.get("line", s.get("hdp", ""))) == next((str(-s2.get("hdp", "")) for s2 in pin_1h.get("spreads", {}).values()), "")), None), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "Spread 1H" and b["selection"] == "Away"), "N/A")},
                {"market": "Total", "selection": "Over", "line": next((str(t.get("points", "")) for t in pin_full_game.get("totals", {}).values()), ""), "pinnacle_nvp": next((t.get("nvp_american_over", None) for t in pin_full_game.get("totals", {}).values()), None), "betbck_odds": bet_data.get("game_total_over_odds"), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "Total" and b["selection"] == "Over"), "N/A")},
                {"market": "Total", "selection": "Under", "line": next((str(t.get("points", "")) for t in pin_full_game.get("totals", {}).values()), ""), "pinnacle_nvp": next((t.get("nvp_american_under", None) for t in pin_full_game.get("totals", {}).values()), None), "betbck_odds": bet_data.get("game_total_under_odds"), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "Total" and b["selection"] == "Under"), "N/A")},
                {"market": "Total 1H", "selection": "Over", "line": next((str(t.get("points", "")) for t in pin_1h.get("totals", {}).values()), ""), "pinnacle_nvp": next((t.get("nvp_american_over", None) for t in pin_1h.get("totals", {}).values()), None), "betbck_odds": bet_data.get("game_total_over_odds_1h"), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "Total 1H" and b["selection"] == "Over"), "N/A")},
                {"market": "Total 1H", "selection": "Under", "line": next((str(t.get("points", "")) for t in pin_1h.get("totals", {}).values()), ""), "pinnacle_nvp": next((t.get("nvp_american_under", None) for t in pin_1h.get("totals", {}).values()), None), "betbck_odds": bet_data.get("game_total_under_odds_1h"), "ev": next((b["ev"] for b in bet_data.get("potential_bets_analyzed", []) if b["market"] == "Total 1H" and b["selection"] == "Under"), "N/A")}
            ]
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

if __name__ == '__main__':
    print("Starting Python Flask server for PODBot...")
    threading.Thread(target=background_event_refresher, daemon=True).start()
    app.run(host='0.0.0.0', port=5001, debug=True, use_reloader=False, threaded=True)