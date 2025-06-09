import requests
from bs4 import BeautifulSoup
import json
import re
import os
import time

try:
    from fuzzywuzzy import fuzz
    FUZZY_MATCH_THRESHOLD = 80
    print("[BetbckScraper] fuzzywuzzy library loaded.")
except ImportError:
    print("[BetbckScraper] WARNING: fuzzywuzzy library not found. Team matching will rely on more exact normalization.")
    fuzz = None
    FUZZY_MATCH_THRESHOLD = 101

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE_PATH = os.path.join(SCRIPT_DIR, 'config.json')
DEFAULT_GAME_WRAPPER_PRIMARY_CLASSES = [
    'table_container_betting Soccer', 'table_container_betting Baseball',
    'table_container_betting Basketball', 'table_container_betting Hockey',
    'table_container_betting American Football', 'table_container_betting Tennis'
]
DEFAULT_GAME_WRAPPER_FALLBACK_CLASSES = ['teams_betting_options_2', 'teams_betting_options']

try:
    with open(CONFIG_FILE_PATH, 'r') as f:
        config = json.load(f)
    betbck_config = config.get('betbck', {})
    LOGIN_PAYLOAD_TEMPLATE = betbck_config.get('credentials')
    BASE_HEADERS = betbck_config.get('headers', {}).copy()
    LOGIN_PAGE_URL = betbck_config.get('login_page_url')
    LOGIN_ACTION_URL = betbck_config.get('login_action_url')
    MAIN_PAGE_URL_AFTER_LOGIN = betbck_config.get('main_page_url_after_login')
    SEARCH_ACTION_URL = betbck_config.get('search_action_url', "https://betbck.com/Qubic/PlayerGameSelection.php")
    GAME_WRAPPER_PRIMARY_CLASSES = betbck_config.get('game_wrapper_primary_classes', DEFAULT_GAME_WRAPPER_PRIMARY_CLASSES)
    GAME_WRAPPER_FALLBACK_CLASSES = betbck_config.get('game_wrapper_fallback_classes', DEFAULT_GAME_WRAPPER_FALLBACK_CLASSES)
except Exception as e:
    print(f"CRITICAL ERROR loading config.json: {e}. Using defaults.")
    LOGIN_PAYLOAD_TEMPLATE, BASE_HEADERS, LOGIN_PAGE_URL, LOGIN_ACTION_URL, MAIN_PAGE_URL_AFTER_LOGIN, SEARCH_ACTION_URL = {}, {}, None, None, None, None
    GAME_WRAPPER_PRIMARY_CLASSES, GAME_WRAPPER_FALLBACK_CLASSES = DEFAULT_GAME_WRAPPER_PRIMARY_CLASSES, DEFAULT_GAME_WRAPPER_FALLBACK_CLASSES

def login_to_betbck(session):
    print(f"[BetbckScraper] Attempting login to BetBCK...")
    try:
        session.get(LOGIN_PAGE_URL, headers=BASE_HEADERS, timeout=10)
        login_response = session.post(LOGIN_ACTION_URL, data=LOGIN_PAYLOAD_TEMPLATE, headers=BASE_HEADERS, allow_redirects=True, timeout=10)
        if ("StraightLoginSportSelection.php" in login_response.url or "MainMenu.php" in login_response.url) and "Logout" in login_response.text:
            print(f"[BetbckScraper] Login SUCCESSFUL.")
            return True
        print(f"[BetbckScraper] Login FAILED. Status: {login_response.status_code}. URL: {login_response.url}")
        return False
    except requests.exceptions.RequestException as e:
        print(f"[BetbckScraper] Login process failed: {e}")
        return False

def get_search_prerequisites(session, page_url):
    print(f"[BetbckScraper] Getting search prerequisites from: {page_url}")
    try:
        response = session.get(page_url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        wager_input = soup.find('input', {'name': 'inetWagerNumber'})
        sport_input = soup.find('input', {'name': 'inetSportSelection'})
        return wager_input.get('value') if wager_input else None, sport_input.get('value', 'sport') if sport_input else 'sport'
    except requests.exceptions.RequestException as e:
        print(f"[BetbckScraper] Failed to get search prerequisites: {e}")
        return None, 'sport'

def search_team_and_get_results_html(session, query, wager_val, sport_val):
    if not all([query, wager_val, sport_val]): return None
    payload = {"action": "Search", "keyword_search": query, "inetWagerNumber": wager_val, "inetSportSelection": sport_val}
    print(f"[BetbckScraper] Searching BetBCK for '{query}'...")
    try:
        response = session.post(SEARCH_ACTION_URL, data=payload, headers=BASE_HEADERS, timeout=15)
        print(f"[BetbckScraper] Search POST successful. Response size: {len(response.text)} bytes.")
        debug_dir = os.path.join(SCRIPT_DIR, "betbck_html_logs")
        os.makedirs(debug_dir, exist_ok=True)
        filename = os.path.join(debug_dir, f"search_{query}_{time.strftime('%Y%m%d_%H%M%S')}.html")
        with open(filename, "w", encoding="utf-8") as f:
            f.write(response.text)
        print(f"[BetbckScraper] DEBUG: Saved search HTML to {filename}")
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"[BetbckScraper] Team search POST failed for '{query}': {e}")
        return None

def normalize_team_name_for_matching(name):
    original_name_for_debug = name
    if not name: return ""
    norm_name = name.lower()
    norm_name = re.sub(r'\s*\([^)]*\)', '', norm_name).strip()
    league_country_suffixes = ['mlb', 'nba', 'nfl', 'nhl', 'ncaaf', 'ncaab',
                               'poland', 'bulgaria', 'uruguay', 'colombia', 'peru',
                               'argentina', 'sweden', 'romania', 'finland', 'fifa',
                               'liga 1', 'serie a', 'bundesliga', 'la liga', 'ligue 1', 'premier league', 'wnba', 'england']
    for suffix in league_country_suffixes:
        pattern = r'(\s+' + re.escape(suffix) + r'|' + re.escape(suffix) + r')$'
        if re.search(pattern, norm_name, flags=re.IGNORECASE):
            temp_name = re.sub(pattern, '', norm_name, flags=re.IGNORECASE, count=1).strip()
            if temp_name or len(norm_name) == len(suffix): norm_name = temp_name
    common_prefixes = ['if ', 'fc ', 'sc ', 'bk ', 'sk ', 'ac ', 'as ', 'fk ', 'cd ', 'ca ', 'afc ', 'cfr ']
    for prefix in common_prefixes:
        if norm_name.startswith(prefix): norm_name = norm_name[len(prefix):].strip(); break
    if "tottenham hotspur" == norm_name: norm_name = "tottenham"
    elif "paris saint germain" in norm_name: norm_name = "psg"
    elif "czechia" in norm_name: norm_name = "czech republic"
    elif "new york" in norm_name: norm_name = norm_name.replace("new york", "ny")
    norm_name = re.sub(r'\s+(fc|sc|cf)$', '', norm_name).strip()
    norm_name = re.sub(r'^[^\w]*(.*?)[^\w]*$', r'\1', norm_name)
    norm_name = re.sub(r'[^\w\s\.\-\+]', '', norm_name)
    final_normalized_name = " ".join(norm_name.split()).strip()
    if original_name_for_debug and original_name_for_debug.lower().strip() != final_normalized_name and final_normalized_name:
        print(f"[NORM_DEBUG] Original: '{original_name_for_debug}' ---> Normalized: '{final_normalized_name}'")
    return final_normalized_name if final_normalized_name else (original_name_for_debug.lower().strip() if original_name_for_debug else "")

def get_cleaned_team_name_from_div(team_div):
    if not team_div: return ""
    name_span = team_div.find('span', {'data-language': True})
    raw_name = name_span.get_text(strip=True) if name_span else None
    if not raw_name:
        text_segments = []
        for content in team_div.children:
            if isinstance(content, str):
                cleaned_str = content.strip()
                text_segments.append(cleaned_str) if cleaned_str else None
            elif content.name == 'span' and content.has_attr('class') and any(cls in content['class'] for cls in ['game_number_local', 'game_number_visitor']): continue
            elif content.name == 'span' and 'font-size:11px' in content.get('style', '').replace(" ", ""): continue
            elif content.name not in ['input', 'br', 'strong'] or (content.name == 'strong' and not content.get_text(strip=True).isdigit()):
                text_segments.append(content.get_text(strip=True))
        raw_name = " ".join(filter(None, text_segments))
    raw_name = re.sub(r'\s*-\s*[A-Za-z\s.]+\s*-\s*[RLrl]\s*(must\s*start|sta\.?)\s*$', '', raw_name, flags=re.IGNORECASE).strip()
    raw_name = re.sub(r'\s*[A-Z]\.\s*[A-Za-z\s.]+\s*-\s*[RLrl]\s*(must\s*start|sta\.?)\s*$', '', raw_name, flags=re.IGNORECASE).strip()
    raw_name = re.sub(r'^\d{3,7}\s*', '', raw_name).strip()
    raw_name = re.sub(r'\s*\((hits\+runs\+errors|h\+r\+e|hre)\)$', '', raw_name, flags=re.IGNORECASE).strip()
    return " ".join(raw_name.split()) if raw_name else ""

def extract_line_value_from_text(text_content_or_td_element, market_type="Spread"):
    if not text_content_or_td_element: return None
    text = ""
    if isinstance(text_content_or_td_element, str):
        text = text_content_or_td_element
    elif hasattr(text_content_or_td_element, 'find'):
        select_el = text_content_or_td_element.find('select')
        if select_el and market_type == "Total":
            option = select_el.find('option', selected=True) or select_el.find('option')
            text = option.get_text(" ", strip=True) if option else select_el.get_text(" ", strip=True)
        else:
            text = text_content_or_td_element.get_text(" ", strip=True)
    else:
        return None
    text = str(text).replace('½', '.5').replace('\u00a0', ' ').strip()
    if market_type == "Total":
        m = re.search(r'[ou]\s*(\d*\.?\d+(?:,\s*\d*\.?\d+)?)', text, re.IGNORECASE)
        if m:
            return normalize_asian_handicap(m.group(1).replace(' ', ''))
    return None

def extract_american_odds_from_text(text_content_or_td_element):
    if not text_content_or_td_element: return None
    text = ""
    if isinstance(text_content_or_td_element, str):
        text = text_content_or_td_element
    elif hasattr(text_content_or_td_element, 'find'):
        select_el = text_content_or_td_element.find('select')
        if select_el:
            option = select_el.find('option', selected=True) or select_el.find('option')
            text = option.get_text(" ", strip=True) if option else select_el.get_text(" ", strip=True)
        else:
            text = text_content_or_td_element.get_text(" ", strip=True)
    else:
        return None
    m = list(re.finditer(r'(?<!\.\d)([+-]\d{3,})', text))
    return m[-1].group(1) if m else None

def normalize_asian_handicap(line_str_input):
    if line_str_input is None:
        return None
    line_str = str(line_str_input).replace('½', '.5').replace(' ', '').replace('\u00a0', '')
    if "pk" in line_str.lower():
        if "," not in line_str:
            return "0"
        parts = [p.strip() for p in line_str.split(',')]
        if len(parts) == 2:
            try:
                v1 = 0.0 if "pk" in parts[0].lower() else float(parts[0])
                v2 = 0.0 if "pk" in parts[1].lower() else float(parts[1])
                avg = (v1 + v2) / 2.0
                fmt = f"{avg:+.2f}" if avg != 0 else "0"
                return fmt[:-3] if fmt.endswith(".00") else fmt.replace(".50", ".5")
            except ValueError:
                return line_str_input
        elif line_str.lower() == "pk":
            return "0"
    if ',' in line_str:
        parts = line_str.split(',')
        if len(parts) == 2:
            try:
                v1, v2 = float(parts[0]), float(parts[1])
                avg = (v1 + v2) / 2.0
                fmt = f"{avg:+.2f}" if avg != 0 else "0"
                return fmt[:-3] if fmt.endswith(".00") else fmt.replace(".50", ".5")
            except ValueError:
                return line_str_input
    try:
        val = float(line_str)
        fmt = f"{val:+.2f}" if val != 0 else "0"
        return fmt[:-3] if fmt.endswith(".00") else fmt.replace(".50", ".5")
    except ValueError:
        return line_str_input

def extract_all_spread_options_from_text(cell_td_element):
    options = []
    if not cell_td_element or not hasattr(cell_td_element, 'find_all'):
        return options
    select_element = cell_td_element.find('select')
    if select_element:
        for option_tag in select_element.find_all('option'):
            option_text = option_tag.get_text(" ", strip=True).replace('½', '.5').replace('\u00a0', ' ')
            match = re.match(r'^\s*([+-]?\d*\.?\d+(?:,\s*[+-]?\d*\.?\d+)?|pk)\s*([+-]\d{3,})', option_text)
            if match:
                raw_line, odds_str = match.group(1).replace(' ', ''), match.group(2)
                norm_line = normalize_asian_handicap(raw_line)
                if norm_line is not None:
                    options.append({"line": norm_line, "odds": odds_str})
    else:
        text_to_parse = cell_td_element.get_text(" ", strip=True).replace('½', '.5').replace('\u00a0', ' ').strip()
        pattern = r'(?:pk|[+-]?\d*\.?\d+(?:,\s*[+-]?\d*\.?\d+)?)\s*([+-]\d{3,})'
        for match in re.finditer(pattern, text_to_parse):
            raw_line, odds_str = match.group(0).split()[0], match.group(1)
            norm_line = normalize_asian_handicap(raw_line)
            if norm_line is not None:
                options.append({"line": norm_line, "odds": odds_str})
    return options

def parse_odds_from_table(odds_table_wrapper, bck_local_is_pod_home, period_suffix=""):
    output = {}
    odds_table = odds_table_wrapper.find('table', class_='new_tb_cont')
    if not odds_table: return output
    data_rows = [r for r in odds_table.find_all('tr', recursive=False) if r.find('td', class_=lambda x: x and 'tbl_betAmount_td' in x)]
    if len(data_rows) < 2: return output
    tds_local, tds_visitor = (data_rows[0].find_all('td'), data_rows[1].find_all('td'))
    h_cells, a_cells = (tds_local, tds_visitor) if bck_local_is_pod_home else (tds_visitor, tds_local)

    if len(h_cells) > 1: output[f"home_moneyline_american{period_suffix}"] = extract_american_odds_from_text(h_cells[1])
    if len(a_cells) > 1: output[f"away_moneyline_american{period_suffix}"] = extract_american_odds_from_text(a_cells[1])
    if len(h_cells) > 0: output[f"home_spreads{period_suffix}"] = extract_all_spread_options_from_text(h_cells[0])
    if len(a_cells) > 0: output[f"away_spreads{period_suffix}"] = extract_all_spread_options_from_text(a_cells[0])
    if len(data_rows) > 2 and "draw" in data_rows[2].get_text(strip=True).lower():
        tds_draw = data_rows[2].find_all('td')
        if len(tds_draw) > 1: output[f"draw_moneyline_american{period_suffix}"] = extract_american_odds_from_text(tds_draw[1])
    return output

def parse_specific_game_from_search_html(html_content, target_home_team_pod, target_away_team_pod):
    if not html_content: print("[BetbckParser] No HTML content."); return None
    soup = BeautifulSoup(html_content, 'html.parser')
    search_context = soup.find('form', {'name': 'GameSelectionForm', 'id': 'GameSelectionForm'}) or soup
    game_wrappers = []
    for gw_class in GAME_WRAPPER_PRIMARY_CLASSES:
        game_wrappers.extend(f for f in search_context.find_all('table', class_=gw_class) if f not in game_wrappers)
    if not game_wrappers and GAME_WRAPPER_FALLBACK_CLASSES:
        print(f"[BetbckParser] No primary wrappers. Fallbacks: {GAME_WRAPPER_FALLBACK_CLASSES}")
        for gw_class in GAME_WRAPPER_FALLBACK_CLASSES:
            for f_table in search_context.find_all('table', class_=gw_class):
                potential_inner = f_table.find_all('table', class_=lambda x: x and x.startswith('table_container_betting'))
                if potential_inner:
                    game_wrappers.extend(iw for iw in potential_inner if iw not in game_wrappers)
                elif f_table.find('table', class_='new_tb_cont') and f_table not in game_wrappers:
                    game_wrappers.append(f_table)
    print(f"[BetbckParser] Found {len(game_wrappers)} potential game wrapper tables.")
    if not game_wrappers: return None

    norm_pod_h = normalize_team_name_for_matching(target_home_team_pod)
    norm_pod_a = normalize_team_name_for_matching(target_away_team_pod)
    print(f"[BetbckParser] Normalized POD Targets: Home='{norm_pod_h}', Away='{norm_pod_a}'")

    for idx, game_wrapper_table in enumerate(game_wrappers):
        team_name_td = game_wrapper_table.find('td', class_=lambda x: x and x.startswith('tbl_betAmount_team1_main_name'))
        if not team_name_td: continue
        div_t1 = team_name_td.find('div', class_='team1_name_up')
        div_t2 = team_name_td.find('div', class_='team2_name_down')
        if not (div_t1 and div_t2): continue
        raw_bck_l, raw_bck_v = get_cleaned_team_name_from_div(div_t1), get_cleaned_team_name_from_div(div_t2)
        if not raw_bck_l or not raw_bck_v:
            print(f"[BetbckParser] Wrapper {idx}: Empty raw names. L='{raw_bck_l}', V='{raw_bck_v}'")
            continue

        skip_indicators = ["1H", "1st Half", "First Half", "1st 5 Innings", "First Five Innings", "1st Period", "2nd Period", "3rd Period", "hits+runs+errors", "h+r+e", "hre", "corners", "series"]
        if any(ind.lower() in raw_bck_l.lower() for ind in skip_indicators) or any(ind.lower() in raw_bck_v.lower() for ind in skip_indicators):
            print(f"[BetbckParser] Skipping non-full game/prop: {raw_bck_l} vs {raw_bck_v}")
            continue

        norm_bck_l, norm_bck_v = normalize_team_name_for_matching(raw_bck_l), normalize_team_name_for_matching(raw_bck_v)
        print(f"[BetbckParser] Comparing POD: H='{norm_pod_h}' A='{norm_pod_a}' WITH BCK {idx}: L='{norm_bck_l}' V='{norm_bck_v}' (Raw: L='{raw_bck_l}', V='{raw_bck_v}')")
        matched, bck_local_is_pod_home = False, False

        if norm_pod_h == norm_bck_l and norm_pod_a == norm_bck_v:
            matched, bck_local_is_pod_home = True, True
            print(f"[BetbckParser] Exact Match (Order 1) for {raw_bck_l} vs {raw_bck_v}")
        elif norm_pod_h == norm_bck_v and norm_pod_a == norm_bck_l:
            matched, bck_local_is_pod_home = True, False
            print(f"[BetbckParser] Exact Match (Order 2 - Flipped) for {raw_bck_l} vs {raw_bck_v}")
        elif fuzz:
            s_hl = fuzz.token_set_ratio(norm_pod_h, norm_bck_l)
            s_av = fuzz.token_set_ratio(norm_pod_a, norm_bck_v)
            s_hv = fuzz.token_set_ratio(norm_pod_h, norm_bck_v)
            s_al = fuzz.token_set_ratio(norm_pod_a, norm_bck_l)
            print(f"[BetbckParser] Fuzzy Scores for {raw_bck_l} vs {raw_bck_v}: (H-L {s_hl} A-V {s_av}) OR (H-V {s_hv} A-L {s_al})")
            if s_hl >= FUZZY_MATCH_THRESHOLD and s_av >= FUZZY_MATCH_THRESHOLD:
                matched, bck_local_is_pod_home = True, True
                print(f"[BetbckParser] Fuzzy Match (Order 1)")
            elif s_hv >= FUZZY_MATCH_THRESHOLD and s_al >= FUZZY_MATCH_THRESHOLD:
                matched, bck_local_is_pod_home = True, False
                print(f"[BetbckParser] Fuzzy Match (Order 2 - Flipped)")

        if not matched: continue

        print(f"[BetbckParser] Game Matched! BetBCK Local is POD Home: {bck_local_is_pod_home}. Parsing odds...")
        odds_table = game_wrapper_table.find('table', class_='new_tb_cont')
        if not odds_table:
            print(f"[BetbckParser] No 'new_tb_cont' odds table for game {idx}.")
            continue

        output_data = {"source": "betbck.com", "betbck_displayed_local": raw_bck_l, "betbck_displayed_visitor": raw_bck_v,
                       "pod_home_team": target_home_team_pod, "pod_away_team": target_away_team_pod,
                       "home_moneyline_american": None, "away_moneyline_american": None, "draw_moneyline_american": None,
                       "home_spreads": [], "away_spreads": [], "game_total_line": None,
                       "game_total_over_odds": None, "game_total_under_odds": None,
                       "home_team_total_over_line": None, "home_team_total_over_odds": None,
                       "home_team_total_under_line": None, "home_team_total_under_odds": None,
                       "away_team_total_over_line": None, "away_team_total_over_odds": None,
                       "away_team_total_under_line": None, "away_team_total_under_odds": None}

        data_rows_source = odds_table.find('tbody') or odds_table
        all_tr_in_odds_section = data_rows_source.find_all('tr', recursive=False)
        data_rows = [r for r in all_tr_in_odds_section if r.find('td', class_=lambda x: x and 'tbl_betAmount_td' in x) and not r.find('td', colspan=True)]
        print(f"[BetbckParser] Game {idx}: Extracted {len(data_rows)} potential data rows from odds table.")
        if len(data_rows) < 2:
            print(f"[BetbckParser] Insufficient data rows ({len(data_rows)}) for game {idx}.")
            continue

        tds_bck_displayed_local_row = data_rows[0].find_all('td', class_=lambda x: x and 'tbl_betAmount_td' in x)
        tds_bck_displayed_visitor_row = data_rows[1].find_all('td', class_=lambda x: x and 'tbl_betAmount_td' in x)

        h_cells = tds_bck_displayed_local_row if bck_local_is_pod_home else tds_bck_displayed_visitor_row
        a_cells = tds_bck_displayed_visitor_row if bck_local_is_pod_home else tds_bck_displayed_local_row

        if len(h_cells) > 0: output_data["home_spreads"] = extract_all_spread_options_from_text(h_cells[0])
        if len(a_cells) > 0: output_data["away_spreads"] = extract_all_spread_options_from_text(a_cells[0])
        if len(h_cells) > 1: output_data["home_moneyline_american"] = extract_american_odds_from_text(h_cells[1])
        if len(a_cells) > 1: output_data["away_moneyline_american"] = extract_american_odds_from_text(a_cells[1])

        if len(tds_bck_displayed_local_row) > 2:
            total_cell_bck_local = tds_bck_displayed_local_row[2]
            if not output_data.get("game_total_line"):
                output_data["game_total_line"] = extract_line_value_from_text(total_cell_bck_local, "Total")
            if "o" in total_cell_bck_local.get_text(" ", strip=True).lower():
                output_data["game_total_over_odds"] = extract_american_odds_from_text(total_cell_bck_local)
        if len(tds_bck_displayed_visitor_row) > 2:
            total_cell_bck_visitor = tds_bck_displayed_visitor_row[2]
            if not output_data.get("game_total_line"):
                output_data["game_total_line"] = extract_line_value_from_text(total_cell_bck_visitor, "Total")
            if "u" in total_cell_bck_visitor.get_text(" ", strip=True).lower():
                output_data["game_total_under_odds"] = extract_american_odds_from_text(total_cell_bck_visitor)

        if len(h_cells) > 3:
            txt_el = h_cells[3]
            if "o" in txt_el.get_text(" ", strip=True).lower():
                output_data.update({"home_team_total_over_line": extract_line_value_from_text(txt_el, "Total"),
                                  "home_team_total_over_odds": extract_american_odds_from_text(txt_el)})
        if len(h_cells) > 4:
            txt_el = h_cells[4]
            if "u" in txt_el.get_text(" ", strip=True).lower():
                output_data.update({"home_team_total_under_line": extract_line_value_from_text(txt_el, "Total"),
                                  "home_team_total_under_odds": extract_american_odds_from_text(txt_el)})
        if len(a_cells) > 3:
            txt_el = a_cells[3]
            if "o" in txt_el.get_text(" ", strip=True).lower():
                output_data.update({"away_team_total_over_line": extract_line_value_from_text(txt_el, "Total"),
                                  "away_team_total_over_odds": extract_american_odds_from_text(txt_el)})
        if len(a_cells) > 4:
            txt_el = a_cells[4]
            if "u" in txt_el.get_text(" ", strip=True).lower():
                output_data.update({"away_team_total_under_line": extract_line_value_from_text(txt_el, "Total"),
                                  "away_team_total_under_odds": extract_american_odds_from_text(txt_el)})

        if len(data_rows) > 2 and "draw" in data_rows[2].get_text(strip=True).lower():
            tds_draw = data_rows[2].find_all('td', class_=lambda x: x and 'tbl_betAmount_td' in x)
            if len(tds_draw) > 1:
                output_data["draw_moneyline_american"] = extract_american_odds_from_text(tds_draw[1])

        print(f"[BetbckParser] Final Parsed Data: {json.dumps(output_data, indent=2)}")
        return output_data

    print(f"[BetbckParser] No game matching POD teams found after all wrappers.")
    return None

def scrape_betbck_for_game(pod_home_team, pod_away_team, search_team_name_betbck=None):
    print(f"\n[BetbckScraper-CORE] Initiating scrape for: '{pod_home_team}' vs '{pod_away_team}'")
    session = requests.Session()
    if not login_to_betbck(session):
        print("[BetbckScraper-CORE] Login failed.")
        return None
    inet_wager, inet_sport_select = get_search_prerequisites(session, MAIN_PAGE_URL_AFTER_LOGIN)
    if not inet_wager:
        print("[BetbckScraper-CORE] Failed to get inetWagerNumber.")
        return None
    actual_search_query = search_team_name_betbck
    if not actual_search_query:
        temp_cleaned_home = normalize_team_name_for_matching(pod_home_team)
        home_parts = temp_cleaned_home.split()
        if home_parts:
            if len(home_parts) > 1 and len(home_parts[-1]) > 3 and home_parts[-1].lower() not in ['fc', 'sc', 'united', 'city', 'club', 'de', 'do', 'ac', 'if', 'bk', 'aif', 'kc']:
                actual_search_query = home_parts[-1]
            elif len(home_parts[0]) > 2 and home_parts[0].lower() not in ['fc', 'sc', 'ac', 'if', 'bk', 'de', 'do', 'aif', 'kc']:
                actual_search_query = home_parts[0]
            else:
                actual_search_query = temp_cleaned_home
        else:
            actual_search_query = pod_home_team
        print(f"[BetbckScraper-CORE] Derived search query '{actual_search_query}' from '{pod_home_team}'")
    print(f"[BetbckScraper-CORE] Using BetBCK search query: '{actual_search_query}'")
    search_results_html = search_team_and_get_results_html(session, actual_search_query, inet_wager, inet_sport_select or 'sport')
    if not search_results_html:
        print(f"[BetbckScraper-CORE] No search results HTML for '{actual_search_query}'.")
        return None
    debug_html_dir = os.path.join(SCRIPT_DIR, "betbck_html_logs")
    os.makedirs(debug_html_dir, exist_ok=True)
    safe_pod_home = re.sub(r'[^\w\-_.]', '_', normalize_team_name_for_matching(pod_home_team))
    safe_pod_away = re.sub(r'[^\w\-_.]', '_', normalize_team_name_for_matching(pod_away_team))
    pod_teams_fn_part = f"{safe_pod_home}_vs_{safe_pod_away}"[:100]
    safe_search_q = re.sub(r'[^\w\-_.]', '_', actual_search_query)
    ts = time.strftime('%Y%m%d_%H%M%S')
    debug_fn = os.path.join(debug_html_dir, f"search_{safe_search_q}_{pod_teams_fn_part}_{ts}.html")
    try:
        with open(debug_fn, "w", encoding="utf-8") as f:
            f.write(search_results_html)
        print(f"[BetbckScraper-CORE] DEBUG: Saved BetBCK search HTML to {debug_fn}")
    except Exception as e:
        print(f"[BetbckScraper-CORE] DEBUG: ERROR saving HTML: {e}")
    parsed_game_data = parse_specific_game_from_search_html(search_results_html, pod_home_team, pod_away_team)
    if parsed_game_data:
        print(f"[BetbckScraper-CORE] Scraper returned parsed game data.")
    else:
        print(f"[BetbckScraper-CORE] Scraper did NOT find or parse specific game from HTML.")
    return parsed_game_data