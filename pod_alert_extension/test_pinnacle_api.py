import requests
import json
from datetime import datetime

# EVENT_ID from your example POD alert JSON data
TEST_EVENT_ID = "1609669590" # Nautico vs Sao Paulo

# THIS IS THE CORRECT API ENDPOINT BASED ON YOUR SCREENSHOT image_c24d2e.png
PINNACLE_EVENT_API_URL = f"https://swordfish-production.up.railway.app/events/{TEST_EVENT_ID}"

# Mimic headers from your screenshot image_c24d2e.png
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    "Accept": "*/*", # As seen in your screenshot
    "Accept-Encoding": "gzip, deflate, br, zstd", # Browser usually handles this
    "Accept-Language": "en-US,en;q=0.9",
    "Origin": "https://www.pinnacleoddsdropper.com", # Important for CORS
    "Referer": "https://www.pinnacleoddsdropper.com/", # Important for context
    "Sec-Ch-Ua": '"Chromium";v="136", "Google Chrome";v="136", "Not:A-Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "cross-site", # This indicates the API is on a different domain than pinnacleoddsdropper.com itself
    # Add any other headers if needed, but these are the main ones from your screenshot
}

def fetch_pinnacle_event_odds_from_swordfish(event_id):
    """Fetches all live lines for a given event_id from the Swordfish API that POD uses."""
    url = f"https://swordfish-production.up.railway.app/events/{event_id}"
    print(f"Attempting to fetch: {url}")
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()
        
        print(f"Status Code: {response.status_code}")
        # The content encoding is 'br' (Brotli) as per your screenshot
        # The requests library usually handles Brotli automatically if the `brotli` package is installed.
        # If not, you might need to install it: pip install brotli requests[brotli]
        # And then decompress manually if requests doesn't, but it usually does.
        
        odds_data = response.json() # Assuming it returns JSON directly
        return odds_data

    except requests.exceptions.HTTPError as http_err:
        print(f"HTTP error occurred: {http_err}")
        print(f"Response content: {response.content[:500]}") # Show beginning of content if error
    except requests.exceptions.RequestException as req_err:
        print(f"Request error occurred: {req_err}")
    except json.JSONDecodeError as json_err:
        print(f"Failed to decode JSON: {json_err}")
        print(f"Response content received that failed to parse: {response.text[:1000]}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
    return None

if __name__ == "__main__":
    print(f"Fetching detailed odds for Pinnacle Event ID (via Swordfish API): {TEST_EVENT_ID}")
    live_odds_data = fetch_pinnacle_event_odds_from_swordfish(TEST_EVENT_ID)

    if live_odds_data:
        print("\nSuccessfully fetched and parsed Pinnacle odds data (via Swordfish API)!")
        
        filename = f"swordfish_pinnacle_event_{TEST_EVENT_ID}_data.json"
        with open(filename, 'w') as f:
            json.dump(live_odds_data, f, indent=4)
        print(f"Full data saved to: {filename}")

        # Access data based on the structure you provided
        event_data = live_odds_data.get("data", {})
        print(f"\nEvent: {event_data.get('home')} vs {event_data.get('away')}")
        print(f"League: {event_data.get('league_name')}")
        starts_timestamp_ms = event_data.get('starts')
        if starts_timestamp_ms:
              print(f"Starts: {datetime.fromtimestamp(starts_timestamp_ms / 1000)}")
        
        game_period_odds = event_data.get("periods", {}).get("num_0", {})
        if game_period_odds:
            print("\n--- Game Period Odds (num_0) ---")
            if "money_line" in game_period_odds:
                print("Moneyline:", game_period_odds["money_line"])
            if "spreads" in game_period_odds and game_period_odds["spreads"]:
                first_spread_key = list(game_period_odds["spreads"].keys())[0]
                print(f"Example Spread ({first_spread_key}):", game_period_odds["spreads"][first_spread_key])
            if "totals" in game_period_odds and game_period_odds["totals"]:
                first_total_key = list(game_period_odds["totals"].keys())[0]
                print(f"Example Total ({first_total_key}):", game_period_odds["totals"][first_total_key])
        else:
            print("No 'num_0' (Game period) odds found in the data.")
    else:
        print("\nFailed to fetch or parse Pinnacle odds data (via Swordfish API).")