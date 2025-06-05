from flask import Flask, render_template, request, jsonify, redirect
import requests
import json
import math
from flask_cors import CORS
from datetime import datetime

app = Flask(__name__)
CORS(app, resources={r"/realtime/*": {"origins": "chrome-extension://*"}})

odds_storage = {}

@app.template_filter('format_timestamp')
def format_timestamp(timestamp):
    if not timestamp:
        return 'N/A'
    try:
        return datetime.fromtimestamp(timestamp / 1000).strftime('%Y-%m-%d %H:%M:%S')
    except (ValueError, TypeError):
        return 'N/A'

def adjust_power(probabilities, tolerance=1e-4, max_iterations=100):
    """Adjust probabilities using the Power Method with Newton-Raphson iterations."""
    k = 1.0
    adjusted_probs = [math.pow(prob, k) for prob in probabilities if prob > 0]

    for i in range(max_iterations):
        overround = sum(adjusted_probs) - 1
        if abs(overround) < tolerance:
            break
        denominator = sum(math.log(prob) * math.pow(prob, k) for prob in probabilities if prob > 0)
        if denominator == 0:  # Avoid division by zero
            break
        k -= overround / denominator
        adjusted_probs = [math.pow(prob, k) for prob in probabilities if prob > 0]

    # Normalize to sum to 1
    total_adjusted = sum(adjusted_probs)
    if total_adjusted > 0:
        adjusted_probs = [p / total_adjusted for p in adjusted_probs]
    else:
        adjusted_probs = [1.0 / len(probabilities)] * len(probabilities)  # Fallback

    return adjusted_probs

def calculate_nvp_power_method(odds_list):
    """Calculate No-Vig Prices using the Power Method based on POD's implementation."""
    # Filter out None values and invalid odds (≤ 1)
    valid_odds = [odd for odd in odds_list if odd is not None and odd > 1]
    if len(valid_odds) < 2:
        return [None] * len(odds_list)

    # Calculate initial implied probabilities
    implied_probs = [1 / odd for odd in valid_odds]

    # Adjust probabilities using Power Method
    adjusted_probs = adjust_power(implied_probs)

    # Convert back to odds
    nvps = [1 / p if p > 0 else None for p in adjusted_probs]

    # Map back to the original list
    result = []
    valid_idx = 0
    for odd in odds_list:
        if odd is not None and odd > 1:
            result.append(round(nvps[valid_idx], 3) if nvps[valid_idx] else None)
            valid_idx += 1
        else:
            result.append(None)
    return result

def cleanup_expired_odds():
    current_time = int(datetime.now().timestamp() * 1000)
    expired_events = []
    for event_id, data in odds_storage.items():
        # Remove if older than 3 minutes (180,000 ms)
        if current_time - data['added_time'] > 180000:  # 3 minutes
            expired_events.append(event_id)
    for event_id in expired_events:
        del odds_storage[event_id]
        print(f"Removed expired event_id {event_id} from odds_storage")

@app.route('/realtime/<event_id>', methods=['POST'])
def fetch_odds(event_id):
    print(f"Received POST request for eventId: {event_id} at {datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
    print(f"Request headers: {request.headers}")
    cookies = request.headers.get('X-Custom-Cookies', '')
    if not cookies:
        print("No cookies provided in request headers")
        return {"status": "failed", "reason": "No cookies provided"}, 400

    print(f"Received cookies: {cookies}")
    api_url = f"https://www.pinnacleoddsdropper.com/api/trpc/events.getEvent?batch=1&input={requests.utils.quote(json.dumps({'0': {'json': f'events:{event_id}'}}))}"
    try:
        headers = {"Cookie": cookies}
        response = requests.get(api_url, headers=headers)
        response.raise_for_status()
        data = response.json()
        print(f"Full API Response for eventId {event_id}: {json.dumps(data, indent=2)}")
        odds_data = data[0]['result']['data']['json']['document']['value'] if data and data[0] else {}
        if not odds_data:
            print(f"No odds data found for eventId: {event_id}")
            return {"status": "failed", "reason": "No odds data found"}, 404

        # Calculate NVP for each market using Power Method
        periods = odds_data.get("periods", {})
        period0 = periods.get("num_0", {})  # Full match
        period1 = periods.get("num_1", {})  # First half

        # Money Line (Full Match)
        if period0.get("money_line"):
            money_line = period0["money_line"]
            vig_home, vig_draw, vig_away = money_line.get("home"), money_line.get("draw"), money_line.get("away")
            nvps = calculate_nvp_power_method([vig_home, vig_draw, vig_away])
            if len(nvps) == 3:
                money_line["nvp_home"], money_line["nvp_draw"], money_line["nvp_away"] = nvps
            print(f"Money Line (Full) - Vig: Home {vig_home}, Draw {vig_draw}, Away {vig_away}, NVP: Home {money_line.get('nvp_home')}, Draw {money_line.get('nvp_draw')}, Away {money_line.get('nvp_away')}")

        # Spreads (Full Match)
        if period0.get("spreads"):
            for hdp, spread in period0["spreads"].items():
                vig_home, vig_away = spread.get("home"), spread.get("away")
                nvps = calculate_nvp_power_method([vig_home, vig_away])
                if len(nvps) == 2:
                    spread["nvp_home"], spread["nvp_away"] = nvps
                print(f"Spread (Full) {hdp} - Vig: Home {vig_home}, Away {vig_away}, NVP: Home {spread.get('nvp_home')}, Away {spread.get('nvp_away')}")

        # Totals (Full Match)
        if period0.get("totals"):
            for points, total in period0["totals"].items():
                vig_over, vig_under = total.get("over"), total.get("under")
                nvps = calculate_nvp_power_method([vig_over, vig_under])
                if len(nvps) == 2:
                    total["nvp_over"], total["nvp_under"] = nvps
                print(f"Total (Full) {points} - Vig: Over {vig_over}, Under {vig_under}, NVP: Over {total.get('nvp_over')}, Under {total.get('nvp_under')}")

        # Money Line (First Half)
        if period1.get("money_line"):
            money_line = period1["money_line"]
            vig_home, vig_draw, vig_away = money_line.get("home"), money_line.get("draw"), money_line.get("away")
            nvps = calculate_nvp_power_method([vig_home, vig_draw, vig_away])
            if len(nvps) == 3:
                money_line["nvp_home"], money_line["nvp_draw"], money_line["nvp_away"] = nvps
            print(f"Money Line (First Half) - Vig: Home {vig_home}, Draw {vig_draw}, Away {vig_away}, NVP: Home {money_line.get('nvp_home')}, Draw {money_line.get('nvp_draw')}, Away {money_line.get('nvp_away')}")

        # Totals (First Half)
        if period1.get("totals"):
            for points, total in period1["totals"].items():
                vig_over, vig_under = total.get("over"), total.get("under")
                nvps = calculate_nvp_power_method([vig_over, vig_under])
                if len(nvps) == 2:
                    total["nvp_over"], total["nvp_under"] = nvps
                print(f"Total (First Half) {points} - Vig: Over {vig_over}, Under {vig_under}, NVP: Over {total.get('nvp_over')}, Under {total.get('nvp_under')}")

        current_time = int(datetime.now().timestamp() * 1000)
        print(f"Setting current_time: {current_time} at {datetime.fromtimestamp(current_time / 1000).strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}")
        odds_storage[event_id] = {
            'odds': odds_data,
            'added_time': current_time,
            'last_updated': current_time,
            'alert_outcome': request.headers.get('X-Alert-Outcome', '')
        }
        print(f"odds_storage after update (raw timestamps): { {eid: {'added_time': d['added_time'], 'last_updated': d['last_updated'], 'alert_outcome': d.get('alert_outcome', 'N/A')} for eid, d in odds_storage.items()} }")
        print(f"odds_storage after update: { {eid: {'added_time': datetime.fromtimestamp(d['added_time'] / 1000).strftime('%Y-%m-%d %H:%M:%S'), 'last_updated': datetime.fromtimestamp(d['last_updated'] / 1000).strftime('%Y-%m-%d %H:%M:%S'), 'alert_outcome': d.get('alert_outcome', 'N/A')} for eid, d in odds_storage.items()} }")
        return {"status": "success", "odds_data": odds_data}
    except Exception as e:
        print(f"Error fetching odds for eventId {event_id}: {e}")
        return {"status": "failed", "reason": str(e)}, 500

# Add a redirect response to /odds_table to prevent browser window opening
@app.route('/odds_table')
def odds_table():
    print("Received request for /odds_table - redirecting to prevent browser window")
    return redirect("http://localhost:5000/get_odds_data", code=302)

@app.route('/get_odds_data', methods=['GET'])
def get_odds_data():
    cleanup_expired_odds()
    sorted_odds = dict(sorted(odds_storage.items(), key=lambda x: x[1]['added_time'], reverse=True))
    current_time = int(datetime.now().timestamp() * 1000)
    print(f"Before sorting in /get_odds_data (raw timestamps): { {eid: {'added_time': d['added_time'], 'last_updated': d['last_updated']} for eid, d in sorted_odds.items()} }")
    print(f"Sorted odds_storage for /get_odds_data (raw timestamps): { {eid: {'added_time': d['added_time'], 'last_updated': d['last_updated']} for eid, d in sorted_odds.items()} }")
    print(f"Sorted odds_storage for /get_odds_data: { {eid: {'added_time': datetime.fromtimestamp(d['added_time'] / 1000).strftime('%Y-%m-%d %H:%M:%S'), 'last_updated': datetime.fromtimestamp(d['last_updated'] / 1000).strftime('%Y-%m-%d %H:%M:%S')} for eid, d in sorted_odds.items()} }")
    return jsonify({'odds_data': sorted_odds, 'server_time': current_time})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)