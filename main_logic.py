import traceback
import re
import math

try:
    from betbck_scraper import scrape_betbck_for_game
    print("[MainLogic] SUCCESS: 'scrape_betbck_for_game' imported successfully.")
except ImportError as e:
    print(f"[MainLogic] CRITICAL_ERROR: {e}")
    raise

def american_to_decimal(american_odds):
    if american_odds is None: return None
    try:
        odds = float(str(american_odds).replace('PK', '0'))
        if odds > 0: return (odds / 100) + 1
        return (100 / abs(odds)) + 1
    except (ValueError, TypeError): return None

def calculate_ev(bet_decimal_odds, true_decimal_odds):
    if not all([bet_decimal_odds, true_decimal_odds]) or true_decimal_odds <= 1.0: return None
    ev = (bet_decimal_odds / true_decimal_odds) - 1
    return ev if -0.5 < ev < 0.20 else None

def clean_pod_team_name_for_search(name_with_extras):
    if not name_with_extras: return ""
    cleaned = re.sub(r'\s*\([^)]*\)', '', name_with_extras).strip()
    league_suffixes = ['mlb', 'nba', 'nfl', 'nhl', 'fifa']
    for suffix in league_suffixes:
        if cleaned.lower().endswith(suffix):
            cleaned = cleaned[:-len(suffix)].strip()
    return cleaned

def determine_betbck_search_term(pod_home, pod_away):
    pod_home_clean = clean_pod_team_name_for_search(pod_home)
    pod_away_clean = clean_pod_team_name_for_search(pod_away)
    known_terms = {
        "south korea": "Korea", "faroe islands": "Faroe", "milwaukee brewers": "Brewers",
        "philadelphia phillies": "Phillies", "los angeles angels": "Angels", "pittsburgh pirates": "Pirates",
        "arizona diamondbacks": "Diamondbacks", "san diego padres": "Padres", "italy": "Italy",
        "st. louis cardinals": "Cardinals", "china pr": "China", "bahrain": "Bahrain", "czechia": "Czech Republic"
    }
    if pod_home_clean.lower() in known_terms: return known_terms[pod_home_clean.lower()]
    parts = pod_home_clean.split()
    return parts[-1] if len(parts) > 1 else pod_home_clean

def analyze_markets_for_ev(bet_data, pinnacle_data):
    """The core analysis function."""
    potential_bets = []
    if not pinnacle_data or not pinnacle_data.get('data'):
        print("[AnalyzeMarkets] No Pinnacle data available")
        return potential_bets

    pin_periods = pinnacle_data['data'].get("periods", {})
    print(f"[AnalyzeMarkets] Raw bet_data: {bet_data}")  # Debug raw data
    print(f"[AnalyzeMarkets] Raw pinnacle_data: {pinnacle_data}")  # Debug pinnacle data

    # Analyze Full Game Markets
    pin_full_game = pin_periods.get("num_0", {})
    if pin_full_game:
        # Moneyline
        if pin_full_game.get("money_line"):
            pin_ml = pin_full_game["money_line"]
            bet_odds = american_to_decimal(bet_data.get("home_moneyline_american"))
            true_odds = american_to_decimal(pin_ml.get("nvp_american_home"))
            ev = calculate_ev(bet_odds, true_odds)
            print(f"[AnalyzeMarkets] Full Game Home ML: Bet={bet_odds}, True={true_odds}, EV={ev}")
            if ev is not None: potential_bets.append({"market": "ML", "selection": "Home", "line": "", "ev": f"{ev*100:.2f}%"})
            bet_odds = american_to_decimal(bet_data.get("away_moneyline_american"))
            true_odds = american_to_decimal(pin_ml.get("nvp_american_away"))
            ev = calculate_ev(bet_odds, true_odds)
            print(f"[AnalyzeMarkets] Full Game Away ML: Bet={bet_odds}, True={true_odds}, EV={ev}")
            if ev is not None: potential_bets.append({"market": "ML", "selection": "Away", "line": "", "ev": f"{ev*100:.2f}%"})
            bet_odds = american_to_decimal(bet_data.get("draw_moneyline_american"))
            true_odds = american_to_decimal(pin_ml.get("nvp_american_draw"))
            ev = calculate_ev(bet_odds, true_odds)
            print(f"[AnalyzeMarkets] Full Game Draw ML: Bet={bet_odds}, True={true_odds}, EV={ev}")
            if ev is not None: potential_bets.append({"market": "ML", "selection": "Draw", "line": "", "ev": f"{ev*100:.2f}%"})

        # Spreads
        if pin_full_game.get("spreads"):
            print(f"[AnalyzeMarkets] Full Game Spreads: {pin_full_game.get('spreads')}")
            for pin_spread in pin_full_game["spreads"].values():
                line = str(pin_spread.get("hdp"))
                bet_spreads_home = bet_data.get("home_spreads", [])
                bet_spreads_away = bet_data.get("away_spreads", [])
                bet_odds_home = next((american_to_decimal(s.get("odds")) for s in bet_spreads_home if str(s.get("line", s.get("hdp", ""))) == line), None)
                true_odds_home = american_to_decimal(pin_spread.get("nvp_american_home"))
                ev = calculate_ev(bet_odds_home, true_odds_home)
                print(f"[AnalyzeMarkets] Full Game Spread Home {line}: Bet={bet_odds_home}, True={true_odds_home}, EV={ev}")
                if ev is not None and {"market": "Spread", "selection": "Home", "line": line} not in [b for b in potential_bets]:
                    potential_bets.append({"market": "Spread", "selection": "Home", "line": line, "ev": f"{ev*100:.2f}%"})
                bet_odds_away = next((american_to_decimal(s.get("odds")) for s in bet_spreads_away if str(s.get("line", s.get("hdp", ""))) == str(-pin_spread.get("hdp"))), None)
                true_odds_away = american_to_decimal(pin_spread.get("nvp_american_away"))
                ev = calculate_ev(bet_odds_away, true_odds_away)
                print(f"[AnalyzeMarkets] Full Game Spread Away {line}: Bet={bet_odds_away}, True={true_odds_away}, EV={ev}")
                if ev is not None and {"market": "Spread", "selection": "Away", "line": str(-pin_spread.get("hdp"))} not in [b for b in potential_bets]:
                    potential_bets.append({"market": "Spread", "selection": "Away", "line": str(-pin_spread.get("hdp")), "ev": f"{ev*100:.2f}%"})

        # Totals
        if pin_full_game.get("totals"):
            print(f"[AnalyzeMarkets] Full Game Totals: {pin_full_game.get('totals')}")
            for pin_total in pin_full_game["totals"].values():
                line = str(pin_total.get("points"))
                bet_odds_over = american_to_decimal(bet_data.get("game_total_over_odds"))
                true_odds_over = american_to_decimal(pin_total.get("nvp_american_over"))
                ev = calculate_ev(bet_odds_over, true_odds_over)
                print(f"[AnalyzeMarkets] Full Game Total Over {line}: Bet={bet_odds_over}, True={true_odds_over}, EV={ev}")
                if ev is not None and {"market": "Total", "selection": "Over", "line": line} not in [b for b in potential_bets]:
                    potential_bets.append({"market": "Total", "selection": "Over", "line": line, "ev": f"{ev*100:.2f}%"})
                bet_odds_under = american_to_decimal(bet_data.get("game_total_under_odds"))
                true_odds_under = american_to_decimal(pin_total.get("nvp_american_under"))
                ev = calculate_ev(bet_odds_under, true_odds_under)
                print(f"[AnalyzeMarkets] Full Game Total Under {line}: Bet={bet_odds_under}, True={true_odds_under}, EV={ev}")
                if ev is not None and {"market": "Total", "selection": "Under", "line": line} not in [b for b in potential_bets]:
                    potential_bets.append({"market": "Total", "selection": "Under", "line": line, "ev": f"{ev*100:.2f}%"})

    # Analyze 1H Markets
    pin_1h = pin_periods.get("num_1", {}) or {}
    if pin_1h:
        if pin_1h.get("money_line"):
            pin_ml_1h = pin_1h["money_line"]
            bet_odds = american_to_decimal(bet_data.get("home_moneyline_american_1h"))
            true_odds = american_to_decimal(pin_ml_1h.get("nvp_american_home"))
            ev = calculate_ev(bet_odds, true_odds)
            print(f"[AnalyzeMarkets] 1H Home ML: Bet={bet_odds}, True={true_odds}, EV={ev}")
            if ev is not None: potential_bets.append({"market": "ML 1H", "selection": "Home", "line": "", "ev": f"{ev*100:.2f}%"})
            bet_odds = american_to_decimal(bet_data.get("away_moneyline_american_1h"))
            true_odds = american_to_decimal(pin_ml_1h.get("nvp_american_away"))
            ev = calculate_ev(bet_odds, true_odds)
            print(f"[AnalyzeMarkets] 1H Away ML: Bet={bet_odds}, True={true_odds}, EV={ev}")
            if ev is not None: potential_bets.append({"market": "ML 1H", "selection": "Away", "line": "", "ev": f"{ev*100:.2f}%"})
            bet_odds = american_to_decimal(bet_data.get("draw_moneyline_american_1h"))
            true_odds = american_to_decimal(pin_ml_1h.get("nvp_american_draw"))
            ev = calculate_ev(bet_odds, true_odds)
            print(f"[AnalyzeMarkets] 1H Draw ML: Bet={bet_odds}, True={true_odds}, EV={ev}")
            if ev is not None: potential_bets.append({"market": "ML 1H", "selection": "Draw", "line": "", "ev": f"{ev*100:.2f}%"})

        # 1H Spreads
        if pin_1h.get("spreads"):
            print(f"[AnalyzeMarkets] 1H Spreads: {pin_1h.get('spreads')}")
            for pin_spread in pin_1h["spreads"].values():
                line = str(pin_spread.get("hdp"))
                bet_spreads_home = bet_data.get("home_spreads_1h", [])
                bet_spreads_away = bet_data.get("away_spreads_1h", [])
                bet_odds_home = next((american_to_decimal(s.get("odds")) for s in bet_spreads_home if str(s.get("line", s.get("hdp", ""))) == line), None)
                true_odds_home = american_to_decimal(pin_spread.get("nvp_american_home"))
                ev = calculate_ev(bet_odds_home, true_odds_home)
                print(f"[AnalyzeMarkets] 1H Spread Home {line}: Bet={bet_odds_home}, True={true_odds_home}, EV={ev}")
                if ev is not None and {"market": "Spread 1H", "selection": "Home", "line": line} not in [b for b in potential_bets]:
                    potential_bets.append({"market": "Spread 1H", "selection": "Home", "line": line, "ev": f"{ev*100:.2f}%"})
                bet_odds_away = next((american_to_decimal(s.get("odds")) for s in bet_spreads_away if str(s.get("line", s.get("hdp", ""))) == str(-pin_spread.get("hdp"))), None)
                true_odds_away = american_to_decimal(pin_spread.get("nvp_american_away"))
                ev = calculate_ev(bet_odds_away, true_odds_away)
                print(f"[AnalyzeMarkets] 1H Spread Away {line}: Bet={bet_odds_away}, True={true_odds_away}, EV={ev}")
                if ev is not None and {"market": "Spread 1H", "selection": "Away", "line": str(-pin_spread.get("hdp"))} not in [b for b in potential_bets]:
                    potential_bets.append({"market": "Spread 1H", "selection": "Away", "line": str(-pin_spread.get("hdp")), "ev": f"{ev*100:.2f}%"})

        # 1H Totals
        if pin_1h.get("totals"):
            print(f"[AnalyzeMarkets] 1H Totals: {pin_1h.get('totals')}")
            for pin_total in pin_1h["totals"].values():
                line = str(pin_total.get("points"))
                bet_odds_over = american_to_decimal(bet_data.get("game_total_over_odds_1h"))
                true_odds_over = american_to_decimal(pin_total.get("nvp_american_over"))
                ev = calculate_ev(bet_odds_over, true_odds_over)
                print(f"[AnalyzeMarkets] 1H Total Over {line}: Bet={bet_odds_over}, True={true_odds_over}, EV={ev}")
                if ev is not None and {"market": "Total 1H", "selection": "Over", "line": line} not in [b for b in potential_bets]:
                    potential_bets.append({"market": "Total 1H", "selection": "Over", "line": line, "ev": f"{ev*100:.2f}%"})
                bet_odds_under = american_to_decimal(bet_data.get("game_total_under_odds_1h"))
                true_odds_under = american_to_decimal(pin_total.get("nvp_american_under"))
                ev = calculate_ev(bet_odds_under, true_odds_under)
                print(f"[AnalyzeMarkets] 1H Total Under {line}: Bet={bet_odds_under}, True={true_odds_under}, EV={ev}")
                if ev is not None and {"market": "Total 1H", "selection": "Under", "line": line} not in [b for b in potential_bets]:
                    potential_bets.append({"market": "Total 1H", "selection": "Under", "line": line, "ev": f"{ev*100:.2f}%"})

    return potential_bets

def process_alert_and_scrape_betbck(event_id, original_alert_details, processed_pinnacle_data, scrape_betbck=True):
    pod_home_team_raw = original_alert_details.get("homeTeam", "")
    pod_away_team_raw = original_alert_details.get("awayTeam", "")

    prop_keywords = ['(Corners)', '(Bookings)', '(Hits+Runs+Errors)']
    if any(keyword.lower() in pod_home_team_raw.lower() for keyword in prop_keywords):
        return {"status": "error_prop_bet", "message": "Alert was for a prop bet."}

    if scrape_betbck:
        search_query = determine_betbck_search_term(pod_home_team_raw, pod_away_team_raw)
        print(f"[MainLogic] Searching BetBCK for '{search_query}'")
        bet_data = scrape_betbck_for_game(pod_home_team_raw, pod_away_team_raw, search_team_name_betbck=search_query)
        if not bet_data:
            return {"status": "error_betbck_scrape_failed", "message": f"Scraper returned no data for search: '{search_query}'"}
    else:
        bet_data = original_alert_details.get("betbck_data", {}).get("data")
        if not bet_data: return {"status": "error", "message": "Re-analysis called but no BetBCK data was found."}

    potential_bets = analyze_markets_for_ev(bet_data, processed_pinnacle_data)
    bet_data["potential_bets_analyzed"] = potential_bets

    if potential_bets:
        print(f"[MainLogic] Analysis complete. Found {len(potential_bets)} potential bet(s).")
        for bet in potential_bets:
            ev_value = float(bet['ev'].strip('%'))
            print(f"  ----> Bet: {bet['market']} {bet['selection']}, EV: {bet['ev']}")
            if ev_value > 0:
                print(f"  ----> POSITIVE EV FOUND: {bet}")
    else:
        print(f"[MainLogic] No potential bets found after analysis.")

    return {"status": "success", "message": "BetBCK odds analyzed.", "data": bet_data}