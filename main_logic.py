import traceback
import re
import math 

_real_scrape_betbck_for_game = None
_scraper_import_error_message = None
_scraper_import_traceback = None

print("[MainLogic] Attempting to import 'scrape_betbck_for_game' from betbck_scraper...")
try:
    from betbck_scraper import scrape_betbck_for_game as _imported_scraper_function
    _real_scrape_betbck_for_game = _imported_scraper_function
    print("[MainLogic] SUCCESS: 'scrape_betbck_for_game' imported successfully.")
except ImportError as e_import:
    _scraper_import_error_message = f"IMPORT ERROR: Failed to import from betbck_scraper.py: {e_import}"
    _scraper_import_traceback = traceback.format_exc() 
    print(f"[MainLogic] {_scraper_import_error_message}")
except Exception as e_general_import:
    _scraper_import_error_message = f"UNEXPECTED ERROR during import from betbck_scraper.py: {e_general_import}"
    _scraper_import_traceback = traceback.format_exc()
    print(f"[MainLogic] {_scraper_import_error_message}")

if not _real_scrape_betbck_for_game:
    def scrape_betbck_for_game(pod_home_team, pod_away_team, search_team_name_betbck=None):
        print("[MainLogic] DUMMY scrape_betbck_for_game CALLED (real scraper unavailable).")
        return {"status": "error_scraper_unavailable", "message": f"BetBCK scraper not loaded: {_scraper_import_error_message or 'Unknown import error'}"}

def american_to_decimal(american_odds):
    if american_odds is None or not isinstance(american_odds, (str, int, float)): return None
    try:
        odds = float(str(american_odds).replace('PK', '0')) 
    except ValueError: return None
    if odds == 0: return None 
    if odds > 0: return (odds / 100) + 1
    if odds < 0: return (100 / abs(odds)) + 1
    return None

def calculate_ev(bet_decimal_odds, true_decimal_odds):
    if not bet_decimal_odds or not true_decimal_odds or true_decimal_odds <= 1.0001 : return None
    return (bet_decimal_odds / true_decimal_odds) - 1

def clean_pod_team_name_for_search(name_with_extras):
    if not name_with_extras: return ""
    cleaned = re.sub(r'\s*\([^)]*\)', '', name_with_extras).strip()
    league_country_suffixes = ['mlb', 'nba', 'nfl', 'nhl', 'ncaaf', 'ncaab', 'poland', 'bulgaria', 'uruguay', 'colombia', 'peru', 'argentina', 'sweden', 'romania', 'finland', 'liga 1', 'serie a', 'bundesliga', 'la liga', 'ligue 1', 'premier league', 'wnba', 'fifa']
    for suffix in league_country_suffixes:
        pattern = r'(\s+' + re.escape(suffix) + r'|' + re.escape(suffix) + r')$'
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            temp_cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE, count=1).strip()
            if temp_cleaned or len(cleaned) == len(suffix): cleaned = temp_cleaned
    return cleaned.strip()

def determine_betbck_search_term(pod_home_team_raw, pod_away_team_raw):
    pod_home_clean = clean_pod_team_name_for_search(pod_home_team_raw)
    pod_away_clean = clean_pod_team_name_for_search(pod_away_team_raw)
    print(f"[MainLogic-SearchTerm] Determining for (cleaned POD): '{pod_home_clean}' vs '{pod_away_clean}'")
    known_terms = {"inter milan":"Inter", "paris sg":"Paris", "boston red sox":"Red Sox", "new york mets":"Mets", "los angeles dodgers":"Dodgers", "universitario de deportes":"Universitario", "deportes tolima":"Tolima", "llaneros":"Llaneros", "patronato parana":"Patronato", "los angeles angels":"Angels", "athletics":"Athletics", "mjällby aif":"Mjallby", "if brommapojkarna":"Brommapojkarna", "rapid bucuresti":"Rapid", "cfr cluj":"Cluj", "slavia sofia": "Sofia", "dallas wings": "Wings", "seattle storm": "Storm"}
    if pod_home_clean.lower() in known_terms: return known_terms[pod_home_clean.lower()]
    if pod_away_clean.lower() in known_terms: return known_terms[pod_away_clean.lower()]
    def get_sig_term(name):
        parts=name.split(); generic=['fc','sc','if','bk','aif','ac','as','cd','ca','afc','de','do','la','san', 'vina', 'del', 'mar', 'st.', 'toronto', 'philadelphia']
        if len(parts)>1 and len(parts[-1])>2 and parts[-1].lower() not in generic: return parts[-1]
        if parts and len(parts[0])>2 and parts[0].lower() not in generic: return parts[0]
        return None
    term=get_sig_term(pod_home_clean)
    if term: return term
    term=get_sig_term(pod_away_clean)
    if term: return term
    return pod_home_clean if pod_home_clean else pod_home_team_raw

def process_alert_and_scrape_betbck(event_id, original_alert_details, processed_pinnacle_data, scrape_betbck=True):
    print(f"\n[MainLogic] process_alert_and_scrape_betbck initiated for Event ID: {event_id}")

    pod_home_team_raw = original_alert_details.get("homeTeam", "")
    pod_away_team_raw = original_alert_details.get("awayTeam", "")
    
    prop_keywords = ['(Corners)', '(Bookings)', '(Hits+Runs+Errors)']
    if any(keyword in pod_home_team_raw for keyword in prop_keywords) or any(keyword in pod_away_team_raw for keyword in prop_keywords):
        print(f"[MainLogic] Alert is for a prop bet. Skipping event {event_id}.")
        return {"status": "error_betbck_scrape_failed", "message": "Alert was for a prop bet, which is not supported."}
    
    if scrape_betbck:
        if not _real_scrape_betbck_for_game: return {"status": "error_scraper_module_unavailable_at_runtime", "message": "BetBCK scraper not loaded."}
        if not pod_home_team_raw or not pod_away_team_raw: return {"status": "error_missing_pod_team_names", "message": "Essential team names missing."}

        betbck_search_query = determine_betbck_search_term(pod_home_team_raw, pod_away_team_raw)
        if isinstance(original_alert_details, dict): original_alert_details['betbck_search_term_used'] = betbck_search_query

        print(f"[MainLogic] POD Teams (Raw): '{pod_home_team_raw}' vs '{pod_away_team_raw}'. BetBCK Search: '{betbck_search_query}'")
        bet_data = _real_scrape_betbck_for_game(pod_home_team_raw, pod_away_team_raw, search_team_name_betbck=betbck_search_query)

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
    pin_data_root = processed_pinnacle_data.get("data", {})
    pin_periods = pin_data_root.get("periods", {})
    pin_full_game = pin_periods.get("num_0", {})
    
    pin_ml = pin_full_game.get("money_line")
    pin_spreads_dict = pin_full_game.get("spreads")
    pin_totals_dict = pin_full_game.get("totals")

    if pin_ml:
        if bet_data.get("home_moneyline_american"):
            ev = calculate_ev(american_to_decimal(bet_data["home_moneyline_american"]), american_to_decimal(pin_ml.get("nvp_american_home")))
            if ev is not None: potential_bets.append({"market":"ML","sel":bet_data["pod_home_team"],"line":"","bck_odds":bet_data["home_moneyline_american"],"pin_nvp":pin_ml.get("nvp_american_home"),"ev":f"{ev*100:.2f}%"})
        if bet_data.get("away_moneyline_american"):
            ev = calculate_ev(american_to_decimal(bet_data["away_moneyline_american"]), american_to_decimal(pin_ml.get("nvp_american_away")))
            if ev is not None: potential_bets.append({"market":"ML","sel":bet_data["pod_away_team"],"line":"","bck_odds":bet_data["away_moneyline_american"],"pin_nvp":pin_ml.get("nvp_american_away"),"ev":f"{ev*100:.2f}%"})
        if bet_data.get("draw_moneyline_american") and pin_ml.get("nvp_american_draw"):
            ev = calculate_ev(american_to_decimal(bet_data["draw_moneyline_american"]), american_to_decimal(pin_ml.get("nvp_american_draw")))
            if ev is not None: potential_bets.append({"market":"ML","sel":"Draw","line":"","bck_odds":bet_data["draw_moneyline_american"],"pin_nvp":pin_ml.get("nvp_american_draw"),"ev":f"{ev*100:.2f}%"})

    if pin_spreads_dict:
        if bet_data.get("home_spreads"):
            for bck_s in bet_data["home_spreads"]:
                try:
                    pin_hdp_key = str(float(bck_s["line"]))
                    if pin_hdp_key == "-0.0": pin_hdp_key = "0.0"
                    pin_s_market = next((s for s_hdp, s in pin_spreads_dict.items() if str(s.get("hdp")) == pin_hdp_key), None)
                    if pin_s_market and pin_s_market.get("nvp_american_home"):
                        ev = calculate_ev(american_to_decimal(bck_s["odds"]), american_to_decimal(pin_s_market.get("nvp_american_home")))
                        if ev is not None: potential_bets.append({"market":"Spread","sel":bet_data["pod_home_team"],"line":bck_s["line"],"bck_odds":bck_s["odds"],"pin_nvp":pin_s_market.get("nvp_american_home"),"ev":f"{ev*100:.2f}%"})
                except (ValueError, TypeError): continue
        if bet_data.get("away_spreads"):
            for bck_s in bet_data["away_spreads"]:
                try:
                    pin_hdp_key = str(-float(bck_s["line"]))
                    if pin_hdp_key == "-0.0": pin_hdp_key = "0.0"
                    pin_s_market = next((s for s_hdp, s in pin_spreads_dict.items() if str(s.get("hdp")) == pin_hdp_key), None)
                    if pin_s_market and pin_s_market.get("nvp_american_away"):
                        ev = calculate_ev(american_to_decimal(bck_s["odds"]), american_to_decimal(pin_s_market.get("nvp_american_away")))
                        if ev is not None: potential_bets.append({"market":"Spread","sel":bet_data["pod_away_team"],"line":bck_s["line"],"bck_odds":bck_s["odds"],"pin_nvp":pin_s_market.get("nvp_american_away"),"ev":f"{ev*100:.2f}%"})
                except (ValueError, TypeError): continue

    if pin_totals_dict:
        bck_total_line = bet_data.get("game_total_line")
        if bck_total_line:
            pin_t_market = pin_totals_dict.get(str(bck_total_line))
            if pin_t_market:
                if bet_data.get("game_total_over_odds") and pin_t_market.get("nvp_american_over"):
                    ev = calculate_ev(american_to_decimal(bet_data["game_total_over_odds"]), american_to_decimal(pin_t_market.get("nvp_american_over")))
                    if ev is not None: potential_bets.append({"market":"Total","sel":"Over","line":bck_total_line,"bck_odds":bet_data["game_total_over_odds"],"pin_nvp":pin_t_market.get("nvp_american_over"),"ev":f"{ev*100:.2f}%"})
                if bet_data.get("game_total_under_odds") and pin_t_market.get("nvp_american_under"):
                    ev = calculate_ev(american_to_decimal(bet_data["game_total_under_odds"]), american_to_decimal(pin_t_market.get("nvp_american_under")))
                    if ev is not None: potential_bets.append({"market":"Total","sel":"Under","line":bck_total_line,"bck_odds":bet_data["game_total_under_odds"],"pin_nvp":pin_t_market.get("nvp_american_under"),"ev":f"{ev*100:.2f}%"})

    if potential_bets:
        print(f"[MainLogic] Potential Bets for Event ID {event_id}:")
        for bet in potential_bets:
            if bet.get("ev") and float(bet["ev"][:-1]) > 0:
                print(f"  DECISION: Consider Bet -> {bet}")
    
    bet_data["potential_bets_analyzed"] = potential_bets
    return {"status": "success", "message": "BetBCK odds analyzed.", "data": bet_data }