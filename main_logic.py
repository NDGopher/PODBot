# main_logic.py
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
    print(f"[MainLogic] Full ImportError traceback:\n{_scraper_import_traceback}")
except Exception as e_general_import:
    _scraper_import_error_message = f"UNEXPECTED ERROR during import from betbck_scraper.py: {e_general_import}"
    _scraper_import_traceback = traceback.format_exc()
    print(f"[MainLogic] {_scraper_import_error_message}")
    print(f"[MainLogic] Full Exception traceback:\n{_scraper_import_traceback}")

if not _real_scrape_betbck_for_game:
    def scrape_betbck_for_game(pod_home_team, pod_away_team, search_team_name_betbck=None):
        print("[MainLogic] DUMMY scrape_betbck_for_game CALLED (real scraper unavailable).")
        return {"status": "error_scraper_unavailable", 
                "message": f"BetBCK scraper not loaded: {_scraper_import_error_message or 'Unknown import error'}",
                "data": None}

def american_to_decimal(american_odds):
    if american_odds is None or not isinstance(american_odds, (str, int, float)): return None
    try:
        odds = float(str(american_odds).replace('PK', '0')) # Handle PK as 0 for odds if it slips in
    except ValueError: return None
    if odds == 0: return None # Or handle as 1.0 if PK implies push? For odds conversion, usually implies no bet.
    if odds > 0: return (odds / 100) + 1
    if odds < 0: return (100 / abs(odds)) + 1
    return None

def calculate_ev(bet_decimal_odds, true_decimal_odds):
    if not bet_decimal_odds or not true_decimal_odds or true_decimal_odds <= 1.0001 : return None
    return (bet_decimal_odds / true_decimal_odds) - 1

def clean_pod_team_name_for_search(name_with_extras):
    if not name_with_extras: return ""
    cleaned = name_with_extras; cleaned = re.sub(r'\s*\([^)]*\)', '', cleaned).strip() 
    league_country_suffixes = ['mlb', 'nba', 'nfl', 'nhl', 'ncaaf', 'ncaab', 'poland', 'bulgaria', 'uruguay', 'colombia', 'peru', 'argentina', 'sweden', 'romania', 'finland', 'liga 1', 'serie a', 'bundesliga', 'la liga', 'ligue 1', 'premier league', 'wnba']
    for suffix in league_country_suffixes:
        pattern = r'(\s+' + re.escape(suffix) + r'|' + re.escape(suffix) + r')$'
        if re.search(pattern, cleaned, flags=re.IGNORECASE):
            temp_cleaned = re.sub(pattern, '', cleaned, flags=re.IGNORECASE, count=1).strip()
            if temp_cleaned or len(cleaned) == len(suffix): cleaned = temp_cleaned
    return cleaned.strip()

def determine_betbck_search_term(pod_home_team_raw, pod_away_team_raw, original_alert_details=None):
    pod_home_clean = clean_pod_team_name_for_search(pod_home_team_raw); pod_away_clean = clean_pod_team_name_for_search(pod_away_team_raw)
    print(f"[MainLogic-SearchTerm] Determining for (cleaned POD): '{pod_home_clean}' vs '{pod_away_clean}'")
    known_terms = {"inter milan":"Inter", "paris sg":"Paris", "boston red sox":"Red Sox", "new york mets":"Mets", "los angeles dodgers":"Dodgers", "universitario de deportes":"Universitario", "deportes tolima":"Tolima", "llaneros":"Llaneros", "patronato parana":"Patronato", "los angeles angels":"Angels", "athletics":"Athletics", "mjällby aif":"Mjallby", "if brommapojkarna":"Brommapojkarna", "rapid bucuresti":"Rapid", "cfr cluj":"Cluj", "slavia sofia": "Sofia", "dallas wings": "Wings", "seattle storm": "Storm"}
    if pod_home_clean.lower() in known_terms: term=known_terms[pod_home_clean.lower()]; print(f"[MainLogic-SearchTerm] Mapped '{term}' for '{pod_home_clean}'"); return term
    if pod_away_clean.lower() in known_terms: term=known_terms[pod_away_clean.lower()]; print(f"[MainLogic-SearchTerm] Mapped '{term}' for '{pod_away_clean}'"); return term
    def get_sig_term(name):
        parts=name.split(); generic=['fc','sc','if','bk','aif','ac','as','cd','ca','afc','de','do','la','san', 'vina', 'del', 'mar', 'st.']
        if len(parts)>1 and len(parts[-1])>2 and parts[-1].lower() not in generic: return parts[-1]
        if parts and len(parts[0])>2 and parts[0].lower() not in generic: return parts[0]
        return None
    term=get_sig_term(pod_home_clean)
    if term: print(f"[MainLogic-SearchTerm] Sig term '{term}' from home '{pod_home_clean}'."); return term
    term=get_sig_term(pod_away_clean)
    if term: print(f"[MainLogic-SearchTerm] Sig term '{term}' from away '{pod_away_clean}'."); return term
    fallback=pod_home_clean if pod_home_clean else pod_home_team_raw; print(f"[MainLogic-SearchTerm] Fallback term '{fallback}'."); return fallback

def process_alert_and_scrape_betbck(event_id, original_alert_details, processed_pinnacle_data):
    print(f"\n[MainLogic] process_alert_and_scrape_betbck initiated for Event ID: {event_id}")

    if not _real_scrape_betbck_for_game:
        print("[MainLogic] Real BetBCK scraper function unavailable. Import failed at startup.")
        return {"status": "error_scraper_module_unavailable_at_runtime", 
                "message": f"BetBCK scraper not loaded: {_scraper_import_error_message or 'Unknown import error'}",
                "event_id": event_id, "data": None, "potential_bets_analyzed": []}

    pod_home_team_raw = original_alert_details.get("homeTeam")
    pod_away_team_raw = original_alert_details.get("awayTeam")
    
    if not pod_home_team_raw or not pod_away_team_raw:
        print("[MainLogic] ERROR: Missing homeTeam or awayTeam from POD alert."); 
        return {"status": "error_missing_pod_team_names", "message": "Essential team names missing.", "event_id": event_id, "data": None, "potential_bets_analyzed": []}

    betbck_search_query = determine_betbck_search_term(pod_home_team_raw, pod_away_team_raw, original_alert_details)
    print(f"[MainLogic] POD Teams (Raw): '{pod_home_team_raw}' vs '{pod_away_team_raw}'. BetBCK Search: '{betbck_search_query}'")

    scraped_betbck_data_response = _real_scrape_betbck_for_game(
        pod_home_team_raw, pod_away_team_raw, search_team_name_betbck=betbck_search_query
    )

    potential_bets = []
    if isinstance(scraped_betbck_data_response, dict) and scraped_betbck_data_response.get("source") == "betbck.com":
        print(f"[MainLogic] Successfully scraped BetBCK data. Analyzing for EV...")
        bet_data = scraped_betbck_data_response # Renamed for clarity inside this block

        # --- Safely Access Pinnacle NVP Data ---
        pin_data_root = processed_pinnacle_data.get("data") if isinstance(processed_pinnacle_data, dict) else {}
        pin_periods = pin_data_root.get("periods") if isinstance(pin_data_root, dict) else {}
        pin_full_game = pin_periods.get("num_0") if isinstance(pin_periods, dict) else {}
        
        pin_ml = pin_full_game.get("money_line") if isinstance(pin_full_game, dict) else {}
        pin_spreads_dict = pin_full_game.get("spreads") if isinstance(pin_full_game, dict) else {} # Pinnacle spreads are dicts
        pin_totals_dict = pin_full_game.get("totals") if isinstance(pin_full_game, dict) else {}   # Pinnacle totals are dicts

        # Moneyline EV
        if bet_data.get("home_moneyline_american"):
            ev = calculate_ev(american_to_decimal(bet_data["home_moneyline_american"]), american_to_decimal(pin_ml.get("nvp_american_home")))
            if ev is not None: potential_bets.append({"market":"ML","sel":bet_data["pod_home_team"],"line":"","bck_odds":bet_data["home_moneyline_american"],"pin_nvp":pin_ml.get("nvp_american_home"),"ev":f"{ev*100:.2f}%"})
        if bet_data.get("away_moneyline_american"):
            ev = calculate_ev(american_to_decimal(bet_data["away_moneyline_american"]), american_to_decimal(pin_ml.get("nvp_american_away")))
            if ev is not None: potential_bets.append({"market":"ML","sel":bet_data["pod_away_team"],"line":"","bck_odds":bet_data["away_moneyline_american"],"pin_nvp":pin_ml.get("nvp_american_away"),"ev":f"{ev*100:.2f}%"})
        if bet_data.get("draw_moneyline_american") and pin_ml.get("nvp_american_draw"):
            ev = calculate_ev(american_to_decimal(bet_data["draw_moneyline_american"]), american_to_decimal(pin_ml.get("nvp_american_draw")))
            if ev is not None: potential_bets.append({"market":"ML","sel":"Draw","line":"","bck_odds":bet_data["draw_moneyline_american"],"pin_nvp":pin_ml.get("nvp_american_draw"),"ev":f"{ev*100:.2f}%"})

        # Spreads EV
        if bet_data.get("home_spreads"):
            for bck_s in bet_data["home_spreads"]:
                pin_s_market = pin_spreads_dict.get(str(bck_s["line"])) # Match line string
                if pin_s_market and pin_s_market.get("nvp_american_home"):
                    ev = calculate_ev(american_to_decimal(bck_s["odds"]), american_to_decimal(pin_s_market.get("nvp_american_home")))
                    if ev is not None: potential_bets.append({"market":"Spread","sel":bet_data["pod_home_team"],"line":bck_s["line"],"bck_odds":bck_s["odds"],"pin_nvp":pin_s_market.get("nvp_american_home"),"ev":f"{ev*100:.2f}%"})
        if bet_data.get("away_spreads"):
            for bck_s in bet_data["away_spreads"]:
                p_hdp_match = str(-float(bck_s["line"])) if bck_s["line"] not in ["0","0.0","pk"] else "0.0"
                if p_hdp_match == "-0.0" : p_hdp_match = "0.0"
                pin_s_market = pin_spreads_dict.get(p_hdp_match)
                if pin_s_market and pin_s_market.get("nvp_american_away"):
                    ev = calculate_ev(american_to_decimal(bck_s["odds"]), american_to_decimal(pin_s_market.get("nvp_american_away")))
                    if ev is not None: potential_bets.append({"market":"Spread","sel":bet_data["pod_away_team"],"line":bck_s["line"],"bck_odds":bck_s["odds"],"pin_nvp":pin_s_market.get("nvp_american_away"),"ev":f"{ev*100:.2f}%"})
        
        # Totals EV
        bck_total_line = bet_data.get("game_total_line")
        if bck_total_line:
            pin_t_market = pin_totals_dict.get(str(bck_total_line)) # Match line string
            if pin_t_market:
                if bet_data.get("game_total_over_odds") and pin_t_market.get("nvp_american_over"):
                    ev = calculate_ev(american_to_decimal(bet_data["game_total_over_odds"]), american_to_decimal(pin_t_market.get("nvp_american_over")))
                    if ev is not None: potential_bets.append({"market":"Total","sel":"Over","line":bck_total_line,"bck_odds":bet_data["game_total_over_odds"],"pin_nvp":pin_t_market.get("nvp_american_over"),"ev":f"{ev*100:.2f}%"})
                if bet_data.get("game_total_under_odds") and pin_t_market.get("nvp_american_under"):
                    ev = calculate_ev(american_to_decimal(bet_data["game_total_under_odds"]), american_to_decimal(pin_t_market.get("nvp_american_under")))
                    if ev is not None: potential_bets.append({"market":"Total","sel":"Under","line":bck_total_line,"bck_odds":bet_data["game_total_under_odds"],"pin_nvp":pin_t_market.get("nvp_american_under"),"ev":f"{ev*100:.2f}%"})

        if potential_bets:
            print(f"[MainLogic] Potential Bets for Event ID {event_id} ({pod_home_team_raw} vs {pod_away_team_raw}):")
            for bet in potential_bets:
                if bet.get("ev") and float(bet["ev"][:-1]) > 0:
                    print(f"  DECISION: Consider Bet -> Market: {bet['market']}, Selection: {bet['sel']}, Line: {bet['line']}, BetBCK Odds: {bet['bck_odds']}, Pin NVP: {bet['pin_nvp']}, EV: {bet['ev']}")
        
        return {"status": "success", "event_id": event_id, "message": "BetBCK odds analyzed.", "data": bet_data, "potential_bets_analyzed": potential_bets }
    else: # Scraper failed or returned unexpected
        error_msg = "Scraper error."
        if isinstance(scraped_betbck_data_response, dict) and "message" in scraped_betbck_data_response: error_msg = scraped_betbck_data_response["message"]
        elif scraped_betbck_data_response is None: error_msg = "Scraper returned no data."
        print(f"[MainLogic] Failed BetBCK scrape for '{pod_home_team_raw}'. Reason: {error_msg}")
        return {"status": "error_betbck_scrape_failed", "message": f"{error_msg} (Searched: '{betbck_search_query}')", "event_id": event_id, "data": None, "potential_bets_analyzed": []}