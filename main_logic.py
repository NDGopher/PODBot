import traceback
import re
import math

try:
    from betbck_scraper import scrape_betbck_for_game
    print("[MainLogic] SUCCESS: 'scrape_betbck_for_game' imported successfully.")
except ImportError as e:
    print(f"[MainLogic] CRITICAL_ERROR: {e}")
    raise

# Import normalize_team_name_for_matching from utils to ensure consistent normalization
from utils import normalize_team_name_for_matching

def american_to_decimal(american_odds):
    if american_odds is None or american_odds == "N/A": return None
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
    return normalize_team_name_for_matching(name_with_extras)

def determine_betbck_search_term(pod_home_team_raw, pod_away_team_raw):
    pod_home_clean = clean_pod_team_name_for_search(pod_home_team_raw)
    pod_away_clean = clean_pod_team_name_for_search(pod_away_team_raw)

    known_terms = {
        "south korea": "Korea", "faroe islands": "Faroe", "milwaukee brewers": "Brewers",
        "philadelphia phillies": "Phillies", "los angeles angels": "Angels", "pittsburgh pirates": "Pirates",
        "arizona diamondbacks": "Diamondbacks", "san diego padres": "Padres", "italy": "Italy",
        "st. louis cardinals": "Cardinals", "china pr": "China", "bahrain": "Bahrain", "czechia": "Czech Republic",
        "athletic club": "Athletic Club", "romania": "Romania", "cyprus": "Cyprus"
    }
    if pod_home_clean.lower() in known_terms:
        return known_terms[pod_home_clean.lower()]
    if pod_away_clean.lower() in known_terms:
        return known_terms[pod_away_clean.lower()]

    parts = pod_home_clean.split()
    if parts:
        if len(parts) > 1 and len(parts[-1]) > 3 and parts[-1].lower() not in ['fc', 'sc', 'united', 'city', 'club', 'de', 'do', 'ac', 'if', 'bk', 'aif', 'kc', 'sr', 'mg', 'us', 'br']:
            return parts[-1]
        elif len(parts[0]) > 2 and parts[0].lower() not in ['fc', 'sc', 'ac', 'if', 'bk', 'de', 'do', 'aif', 'kc', 'sr', 'mg', 'us', 'br']:
            return parts[0]
        else:
            return pod_home_clean
    return pod_home_clean if pod_home_clean else ""

def analyze_markets_for_ev(bet_data, pinnacle_data):
    """The core analysis function. Only include markets with both BetBCK and Pinnacle odds for EV calculation."""
    potential_bets = []
    if not pinnacle_data or not pinnacle_data.get('data'):
        print("[AnalyzeMarkets] No Pinnacle data available")
        return potential_bets

    pin_periods = pinnacle_data['data'].get("periods", {})
    print(f"[MainLogic] Raw bet_data: {bet_data}")
    print(f"[MainLogic] Raw pinnacle_data: {pinnacle_data}")

    # Analyze Full Game Markets
    pin_full_game = pin_periods.get("num_0", {})
    if pin_full_game:
        # Moneyline
        if pin_full_game.get("money_line"):
            pin_ml = pin_full_game["money_line"]
            bet_odds_home = american_to_decimal(bet_data.get("home_moneyline_american"))
            true_odds_home = american_to_decimal(pin_ml.get("nvp_american_home"))
            if bet_odds_home and true_odds_home:
                ev = calculate_ev(bet_odds_home, true_odds_home)
                print(f"[AnalyzeMarkets] Full Game Home ML: Bet={bet_odds_home}, True={true_odds_home}, EV={ev}")
                if ev is not None:
                    potential_bets.append({"market": "ML", "selection": "Home", "line": "", "ev": f"{ev*100:.2f}%"})
            bet_odds_away = american_to_decimal(bet_data.get("away_moneyline_american"))
            true_odds_away = american_to_decimal(pin_ml.get("nvp_american_away"))
            if bet_odds_away and true_odds_away:
                ev = calculate_ev(bet_odds_away, true_odds_away)
                print(f"[AnalyzeMarkets] Full Game Away ML: Bet={bet_odds_away}, True={true_odds_away}, EV={ev}")
                if ev is not None:
                    potential_bets.append({"market": "ML", "selection": "Away", "line": "", "ev": f"{ev*100:.2f}%"})
            bet_odds_draw = american_to_decimal(bet_data.get("draw_moneyline_american"))
            true_odds_draw = american_to_decimal(pin_ml.get("nvp_american_draw"))
            if bet_odds_draw and true_odds_draw:
                ev = calculate_ev(bet_odds_draw, true_odds_draw)
                print(f"[AnalyzeMarkets] Full Game Draw ML: Bet={bet_odds_draw}, True={true_odds_draw}, EV={ev}")
                if ev is not None:
                    potential_bets.append({"market": "ML", "selection": "Draw", "line": "", "ev": f"{ev*100:.2f}%"})

        # Spreads
        if pin_full_game.get("spreads"):
            print(f"[AnalyzeMarkets] Full Game Spreads: {pin_full_game.get('spreads')}")
            for pin_spread in pin_full_game["spreads"].values():
                line = str(pin_spread.get("hdp"))
                bet_spreads_home = bet_data.get("home_spreads", [])
                bet_spreads_away = bet_data.get("away_spreads", [])
                bet_odds_home = next((american_to_decimal(s.get("odds")) for s in bet_spreads_home if str(s.get("line")) == line), None)
                true_odds_home = american_to_decimal(pin_spread.get("nvp_american_home"))
                if bet_odds_home and true_odds_home:
                    ev = calculate_ev(bet_odds_home, true_odds_home)
                    print(f"[AnalyzeMarkets] Full Game Spread Home {line}: Bet={bet_odds_home}, True={true_odds_home}, EV={ev}")
                    if ev is not None:
                        potential_bets.append({"market": "Spread", "selection": "Home", "line": line, "ev": f"{ev*100:.2f}%"})
                bet_odds_away = next((american_to_decimal(s.get("odds")) for s in bet_spreads_away if str(s.get("line")) == str(-pin_spread.get("hdp"))), None)
                true_odds_away = american_to_decimal(pin_spread.get("nvp_american_away"))
                if bet_odds_away and true_odds_away:
                    ev = calculate_ev(bet_odds_away, true_odds_away)
                    print(f"[AnalyzeMarkets] Full Game Spread Away {line}: Bet={bet_odds_away}, True={true_odds_away}, EV={ev}")
                    if ev is not None:
                        potential_bets.append({"market": "Spread", "selection": "Away", "line": str(-pin_spread.get("hdp")), "ev": f"{ev*100:.2f}%"})

        # Totals
        if pin_full_game.get("totals"):
            print(f"[AnalyzeMarkets] Full Game Totals: {pin_full_game.get('totals')}")
            for pin_total in pin_full_game["totals"].values():
                line = str(pin_total.get("points"))
                bet_odds_over = american_to_decimal(bet_data.get("game_total_over_odds"))
                true_odds_over = american_to_decimal(pin_total.get("nvp_american_over"))
                if bet_odds_over and true_odds_over:
                    ev = calculate_ev(bet_odds_over, true_odds_over)
                    print(f"[AnalyzeMarkets] Full Game Total Over {line}: Bet={bet_odds_over}, True={true_odds_over}, EV={ev}")
                    if ev is not None:
                        potential_bets.append({"market": "Total", "selection": "Over", "line": line, "ev": f"{ev*100:.2f}%"})
                bet_odds_under = american_to_decimal(bet_data.get("game_total_under_odds"))
                true_odds_under = american_to_decimal(pin_total.get("nvp_american_under"))
                if bet_odds_under and true_odds_under:
                    ev = calculate_ev(bet_odds_under, true_odds_under)
                    print(f"[AnalyzeMarkets] Full Game Total Under {line}: Bet={bet_odds_under}, True={true_odds_under}, EV={ev}")
                    if ev is not None:
                        potential_bets.append({"market": "Total", "selection": "Under", "line": line, "ev": f"{ev*100:.2f}%"})

    # Analyze 1H Markets
    pin_1h = pin_periods.get("num_1", {})
    if pin_1h:
        if pin_1h.get("money_line"):
            pin_ml_1h = pin_1h["money_line"]
            bet_odds_home = american_to_decimal(bet_data.get("home_moneyline_american_1h"))
            true_odds_home = american_to_decimal(pin_ml_1h.get("nvp_american_home"))
            ev = calculate_ev(bet_odds_home, true_odds_home)
            print(f"[AnalyzeMarkets] 1H Home ML: Bet={bet_odds_home}, True={true_odds_home}, EV={ev}")
            if ev is not None: potential_bets.append({"market": "ML 1H", "selection": "Home", "line": "", "ev": f"{ev*100:.2f}%"})
            bet_odds_away = american_to_decimal(bet_data.get("away_moneyline_american_1h"))
            true_odds_away = american_to_decimal(pin_ml_1h.get("nvp_american_away"))
            ev = calculate_ev(bet_odds_away, true_odds_away)
            print(f"[AnalyzeMarkets] 1H Away ML: Bet={bet_odds_away}, True={true_odds_away}, EV={ev}")
            if ev is not None: potential_bets.append({"market": "ML 1H", "selection": "Away", "line": "", "ev": f"{ev*100:.2f}%"})
            bet_odds_draw = american_to_decimal(bet_data.get("draw_moneyline_american_1h"))
            true_odds_draw = american_to_decimal(pin_ml_1h.get("nvp_american_draw"))
            ev = calculate_ev(bet_odds_draw, true_odds_draw)
            print(f"[AnalyzeMarkets] 1H Draw ML: Bet={bet_odds_draw}, True={true_odds_draw}, EV={ev}")
            if ev is not None: potential_bets.append({"market": "ML 1H", "selection": "Draw", "line": "", "ev": f"{ev*100:.2f}%"})

        # 1H Spreads
        if pin_1h.get("spreads"):
            print(f"[AnalyzeMarkets] 1H Spreads: {pin_1h.get('spreads')}")
            for pin_spread in pin_1h["spreads"].values():
                line = str(pin_spread.get("hdp"))
                bet_spreads_home = bet_data.get("home_spreads_1h", [])
                bet_spreads_away = bet_data.get("away_spreads_1h", [])
                bet_odds_home = next((american_to_decimal(s.get("odds")) for s in bet_spreads_home if str(s.get("line")) == line), None)
                true_odds_home = american_to_decimal(pin_spread.get("nvp_american_home"))
                ev = calculate_ev(bet_odds_home, true_odds_home)
                print(f"[AnalyzeMarkets] 1H Spread Home {line}: Bet={bet_odds_home}, True={true_odds_home}, EV={ev}")
                if ev is not None and {"market": "Spread 1H", "selection": "Home", "line": line} not in [b for b in potential_bets]:
                    potential_bets.append({"market": "Spread 1H", "selection": "Home", "line": line, "ev": f"{ev*100:.2f}%"})
                bet_odds_away = next((american_to_decimal(s.get("odds")) for s in bet_spreads_away if str(s.get("line")) == str(-pin_spread.get("hdp"))), None)
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

    if pin_spreads_dict:
        if bet_data.get("home_spreads"):
            for bck_s in bet_data["home_spreads"]:
                try:
                    bck_line = float(bck_s["line"])
                    pin_s_market = next((s for s in pin_spreads_dict.values() if abs(float(s.get("hdp", 0)) - bck_line) < 0.01), None)
                    if pin_s_market and pin_s_market.get("nvp_american_home"):
                        ev = calculate_ev(american_to_decimal(bck_s["odds"]), american_to_decimal(pin_s_market.get("nvp_american_home")))
                        if ev is not None:
                            potential_bets.append({"market":"Spread","sel":normalize_team_name_for_matching(bet_data["pod_home_team"]),"line":bck_s["line"],"bck_odds":bck_s["odds"],"pin_nvp":pin_s_market.get("nvp_american_home"),"ev":f"{ev*100:.2f}%"})
                except (ValueError, TypeError): continue
        if bet_data.get("away_spreads"):
            for bck_s in bet_data["away_spreads"]:
                try:
                    bck_line = float(bck_s["line"])
                    pin_s_market = next((s for s in pin_spreads_dict.values() if abs(float(s.get("hdp", 0)) + bck_line) < 0.01), None)
                    if pin_s_market and pin_s_market.get("nvp_american_away"):
                        ev = calculate_ev(american_to_decimal(bck_s["odds"]), american_to_decimal(pin_s_market.get("nvp_american_away")))
                        if ev is not None:
                            potential_bets.append({"market":"Spread","sel":normalize_team_name_for_matching(bet_data["pod_away_team"]),"line":bck_s["line"],"bck_odds":bck_s["odds"],"pin_nvp":pin_s_market.get("nvp_american_away"),"ev":f"{ev*100:.2f}%"})
                except (ValueError, TypeError): continue
    if pin_totals_dict:
        bck_total_line = bet_data.get("game_total_line")
        if bck_total_line:
            try:
                bck_total_line_float = float(bck_total_line)
                pin_t_market = next((t for t in pin_totals_dict.values() if abs(float(t.get("points", 0)) - bck_total_line_float) < 0.01), None)
                if pin_t_market:
                    if bet_data.get("game_total_over_odds") and pin_t_market.get("nvp_american_over"):
                        ev = calculate_ev(american_to_decimal(bet_data["game_total_over_odds"]), american_to_decimal(pin_t_market.get("nvp_american_over")))
                        if ev is not None:
                            potential_bets.append({"market":"Total","sel":"Over","line":bck_total_line,"bck_odds":bet_data["game_total_over_odds"],"pin_nvp":pin_t_market.get("nvp_american_over"),"ev":f"{ev*100:.2f}%"})
                    if bet_data.get("game_total_under_odds") and pin_t_market.get("nvp_american_under"):
                        ev = calculate_ev(american_to_decimal(bet_data["game_total_under_odds"]), american_to_decimal(pin_t_market.get("nvp_american_under")))
                        if ev is not None:
                            potential_bets.append({"market":"Total","sel":"Under","line":bck_total_line,"bck_odds":bet_data["game_total_under_odds"],"pin_nvp":pin_t_market.get("nvp_american_under"),"ev":f"{ev*100:.2f}%"})
            except (ValueError, TypeError):
                pass
    bet_data["potential_bets_analyzed"] = potential_bets
    return {"status": "success", "message": "BetBCK odds analyzed.", "data": bet_data }

def process_alert_and_scrape_betbck(event_id, original_alert_details, processed_pinnacle_data, scrape_betbck=True):
    print(f"\n[MainLogic] process_alert_and_scrape_betbck initiated for Event ID: {event_id}")
    pod_home_team_raw = original_alert_details.get("homeTeam", "")
    pod_away_team_raw = original_alert_details.get("awayTeam", "")
    prop_keywords = ['(Corners)', '(Bookings)', '(Hits+Runs+Errors)']
    if any(keyword.lower() in pod_home_team_raw.lower() for keyword in prop_keywords) or any(keyword.lower() in pod_away_team_raw.lower() for keyword in prop_keywords):
        print(f"[MainLogic] Alert is for a prop bet. Skipping event {event_id}.")
        return {"status": "error_prop_bet", "message": "Alert was for a prop bet, which is not supported."}
    if scrape_betbck:
        betbck_search_query = determine_betbck_search_term(pod_home_team_raw, pod_away_team_raw)
        if isinstance(original_alert_details, dict): original_alert_details['betbck_search_term_used'] = betbck_search_query
        print(f"[MainLogic] POD Teams (Raw): '{pod_home_team_raw}' vs '{pod_away_team_raw}'. BetBCK Search: '{betbck_search_query}'")
        bet_data = scrape_betbck_for_game(pod_home_team_raw, pod_away_team_raw, search_team_name_betbck=betbck_search_query)
        if not isinstance(bet_data, dict) or bet_data.get("source") != "betbck.com":
            error_msg = "Scraper returned no data."
            if isinstance(bet_data, dict) and "message" in bet_data: error_msg = bet_data["message"]
            print(f"[MainLogic] Failed BetBCK scrape for '{pod_home_team_raw}'. Reason: {error_msg}")
            return {"status": "error_betbck_scrape_failed", "message": f"{error_msg} (Searched: '{betbck_search_query}')"}
    else:
        bet_data = original_alert_details.get("betbck_comparison_data", {}).get("data")
        if not bet_data: return {"status": "error", "message": "Re-analysis called but no BetBCK data was found."}
    print(f"[MainLogic] Analyzing for EV...")
    potential_bets = []
    pin_data_root = processed_pinnacle_data.get("data") if isinstance(processed_pinnacle_data, dict) else None
    if not pin_data_root:
        print("[MainLogic] ERROR: Pinnacle data is missing or malformed. Cannot analyze for EV.")
        bet_data["potential_bets_analyzed"] = []
        return {"status": "success", "message": "BetBCK odds scraped, but Pinnacle data was missing for analysis.", "data": bet_data }
    pin_periods = pin_data_root.get("periods", {})
    pin_full_game = pin_periods.get("num_0", {})
    pin_ml = pin_full_game.get("money_line")
    pin_spreads_dict = pin_full_game.get("spreads")
    pin_totals_dict = pin_full_game.get("totals")
    if pin_ml:
        if bet_data.get("home_moneyline_american"):
            ev = calculate_ev(american_to_decimal(bet_data["home_moneyline_american"]), american_to_decimal(pin_ml.get("nvp_american_home")))
            if ev is not None:
                potential_bets.append({"market":"ML","sel":normalize_team_name_for_matching(bet_data["pod_home_team"]),"line":"","bck_odds":bet_data["home_moneyline_american"],"pin_nvp":pin_ml.get("nvp_american_home"),"ev":f"{ev*100:.2f}%"})
        if bet_data.get("away_moneyline_american"):
            ev = calculate_ev(american_to_decimal(bet_data["away_moneyline_american"]), american_to_decimal(pin_ml.get("nvp_american_away")))
            if ev is not None:
                potential_bets.append({"market":"ML","sel":normalize_team_name_for_matching(bet_data["pod_away_team"]),"line":"","bck_odds":bet_data["away_moneyline_american"],"pin_nvp":pin_ml.get("nvp_american_away"),"ev":f"{ev*100:.2f}%"})
        if bet_data.get("draw_moneyline_american") and pin_ml.get("nvp_american_draw"):
            ev = calculate_ev(american_to_decimal(bet_data["draw_moneyline_american"]), american_to_decimal(pin_ml.get("nvp_american_draw")))
            if ev is not None:
                potential_bets.append({"market":"ML","sel":"Draw","line":"","bck_odds":bet_data["draw_moneyline_american"],"pin_nvp":pin_ml.get("nvp_american_draw"),"ev":f"{ev*100:.2f}%"})
    if pin_spreads_dict:
        if bet_data.get("home_spreads"):
            for bck_s in bet_data["home_spreads"]:
                try:
                    bck_line = float(bck_s["line"])
                    pin_s_market = next((s for s in pin_spreads_dict.values() if abs(float(s.get("hdp", 0)) - bck_line) < 0.01), None)
                    if pin_s_market and pin_s_market.get("nvp_american_home"):
                        ev = calculate_ev(american_to_decimal(bck_s["odds"]), american_to_decimal(pin_s_market.get("nvp_american_home")))
                        if ev is not None:
                            potential_bets.append({"market":"Spread","sel":normalize_team_name_for_matching(bet_data["pod_home_team"]),"line":bck_s["line"],"bck_odds":bck_s["odds"],"pin_nvp":pin_s_market.get("nvp_american_home"),"ev":f"{ev*100:.2f}%"})
                except (ValueError, TypeError): continue
        if bet_data.get("away_spreads"):
            for bck_s in bet_data["away_spreads"]:
                try:
                    bck_line = float(bck_s["line"])
                    pin_s_market = next((s for s in pin_spreads_dict.values() if abs(float(s.get("hdp", 0)) + bck_line) < 0.01), None)
                    if pin_s_market and pin_s_market.get("nvp_american_away"):
                        ev = calculate_ev(american_to_decimal(bck_s["odds"]), american_to_decimal(pin_s_market.get("nvp_american_away")))
                        if ev is not None:
                            potential_bets.append({"market":"Spread","sel":normalize_team_name_for_matching(bet_data["pod_away_team"]),"line":bck_s["line"],"bck_odds":bck_s["odds"],"pin_nvp":pin_s_market.get("nvp_american_away"),"ev":f"{ev*100:.2f}%"})
                except (ValueError, TypeError): continue
    if pin_totals_dict:
        bck_total_line = bet_data.get("game_total_line")
        if bck_total_line:
            try:
                bck_total_line_float = float(bck_total_line)
                pin_t_market = next((t for t in pin_totals_dict.values() if abs(float(t.get("points", 0)) - bck_total_line_float) < 0.01), None)
                if pin_t_market:
                    if bet_data.get("game_total_over_odds") and pin_t_market.get("nvp_american_over"):
                        ev = calculate_ev(american_to_decimal(bet_data["game_total_over_odds"]), american_to_decimal(pin_t_market.get("nvp_american_over")))
                        if ev is not None:
                            potential_bets.append({"market":"Total","sel":"Over","line":bck_total_line,"bck_odds":bet_data["game_total_over_odds"],"pin_nvp":pin_t_market.get("nvp_american_over"),"ev":f"{ev*100:.2f}%"})
                    if bet_data.get("game_total_under_odds") and pin_t_market.get("nvp_american_under"):
                        ev = calculate_ev(american_to_decimal(bet_data["game_total_under_odds"]), american_to_decimal(pin_t_market.get("nvp_american_under")))
                        if ev is not None:
                            potential_bets.append({"market":"Total","sel":"Under","line":bck_total_line,"bck_odds":bet_data["game_total_under_odds"],"pin_nvp":pin_t_market.get("nvp_american_under"),"ev":f"{ev*100:.2f}%"})
            except (ValueError, TypeError):
                pass
    bet_data["potential_bets_analyzed"] = potential_bets
    return {"status": "success", "message": "BetBCK odds analyzed.", "data": bet_data }

def process_pod_alert(alert_data):
    """Process a POD alert and update the active events"""
    try:
        # Extract event ID and search term
        event_id = alert_data.get('event_id')
        search_term = alert_data.get('search_term', '').lower()
        
        if not event_id or not search_term:
            print(f"[MainLogic] Invalid alert data: {alert_data}")
            return
            
        print(f"[MainLogic] Processing alert for Event ID: {event_id}")
        
        # Get event details from Pinnacle
        pinnacle_data = fetch_pinnacle_event(event_id)
        if not pinnacle_data:
            print(f"[MainLogic] Failed to fetch Pinnacle data for event {event_id}")
            return
            
        # Extract team names and league from Pinnacle data
        home_team = pinnacle_data.get('home', {}).get('name', '')
        away_team = pinnacle_data.get('away', {}).get('name', '')
        league = pinnacle_data.get('league', {}).get('name', '')
        start_time = pinnacle_data.get('starts', '')
        
        # Search BetBCK
        print(f"[MainLogic] Searching BetBCK for '{search_term}'")
        betbck_data = search_betbck(search_term)
        
        if not betbck_data:
            print(f"[MainLogic] No BetBCK data found for '{search_term}'")
            return
            
        # Create event data
        event_data = {
            'event_id': event_id,
            'home_team': home_team,
            'away_team': away_team,
            'league': league,
            'start_time': start_time,
            'pinnacle_odds': pinnacle_data.get('odds', {}),
            'betbck_odds': betbck_data
        }
        
        # Add to active events
        active_events[event_id] = event_data
        print(f"[MainLogic] Added event {event_id} to active events")
        
        # Save to file
        save_active_events()
        
    except Exception as e:
        print(f"[MainLogic] Error processing POD alert: {str(e)}")
        traceback.print_exc()