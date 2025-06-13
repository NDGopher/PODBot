import math
import re

def normalize_team_name_for_matching(name):
    original_name_for_debug = name
    if name is None or not name:  # Explicitly check for None
        print(f"[Utils] WARNING: normalize_team_name_for_matching received None or empty input: '{original_name_for_debug}'")
        return ""

    # Handle common phrases indicating a prop/future first
    trophy_match = re.match(r'(.+?)\s*(?:to lift the trophy|lift the trophy|to win.*|wins.*|\(match\)|series price|to win series|\(corners\))', name, re.IGNORECASE)
    if trophy_match:
        name = trophy_match.group(1).strip()

    norm_name = name.lower()
    norm_name = re.sub(r'\s*\((?:games|sets|match|hits\+runs\+errors|h\+r\+e|hre|corners)\)$', '', norm_name).strip()
    norm_name = re.sub(r'\s*\([^)]*\)', '', norm_name).strip()

    league_country_suffixes = [
        'mlb', 'nba', 'nfl', 'nhl', 'ncaaf', 'ncaab', 'wnba',
        'poland', 'bulgaria', 'uruguay', 'colombia', 'peru', 'argentina', 
        'sweden', 'romania', 'finland', 'england', 'japan', 'austria',
        'liga 1', 'serie a', 'bundesliga', 'la liga', 'ligue 1', 'premier league',
        'epl', 'mls', 'tipico bundesliga', 'belarus'
    ]
    for suffix in league_country_suffixes:
        pattern = r'(\s+' + re.escape(suffix) + r'|' + re.escape(suffix) + r')$'
        if re.search(pattern, norm_name, flags=re.IGNORECASE):
            temp_name = re.sub(pattern, '', norm_name, flags=re.IGNORECASE, count=1).strip()
            if temp_name or len(norm_name) == len(suffix): 
                norm_name = temp_name

    common_prefixes = ['if ', 'fc ', 'sc ', 'bk ', 'sk ', 'ac ', 'as ', 'fk ', 'cd ', 'ca ', 'afc ', 'cfr ', 'kc ', 'scr ']
    for prefix in common_prefixes: 
        if norm_name.startswith(prefix): norm_name = norm_name[len(prefix):].strip()
    for prefix in common_prefixes: 
        if norm_name.startswith(prefix): norm_name = norm_name[len(prefix):].strip()

    if "tottenham hotspur" in name.lower(): norm_name = "tottenham" 
    elif "paris saint germain" in name.lower() or "paris sg" in name.lower(): norm_name = "psg"
    elif "new york" in name.lower(): norm_name = norm_name.replace("new york", "ny")
    elif "los angeles" in name.lower(): norm_name = norm_name.replace("los angeles", "la")
    elif "st louis" in name.lower(): norm_name = norm_name.replace("st louis", "st. louis") 
    elif "inter milan" in name.lower() or name.lower() == "internazionale": norm_name = "inter"
    elif "rheindorf altach" in name.lower(): norm_name = "altach" 
    elif "scr altach" in name.lower(): norm_name = "altach"
    
    norm_name = re.sub(r'^[^\w]+|[^\w]+$', '', norm_name) 
    norm_name = re.sub(r'[^\w\s\.\-\+]', '', norm_name) 
    final_normalized_name = " ".join(norm_name.split()).strip() 
    return final_normalized_name if final_normalized_name else (original_name_for_debug.lower().strip() if original_name_for_debug else "")

def get_cleaned_team_name_from_div(team_div_soup):
    if not team_div_soup: return ""
    raw_name_text = ""
    name_span = team_div_soup.find('span', {'data-language': True})
    if name_span:
        raw_name_text = name_span.get_text(separator=' ', strip=True)
    
    if not raw_name_text:
        text_segments = []
        for content in team_div_soup.children:
            if isinstance(content, str):
                cleaned_str = content.strip()
                if cleaned_str: text_segments.append(cleaned_str)
            elif content.name == 'span' and content.has_attr('class') and any(cls in content['class'] for cls in ['game_number_local', 'game_number_visitor']):
                continue
            elif content.name == 'span' and 'font-size:11px' in content.get('style','').replace(" ", ""):
                continue
            elif content.name == 'br':
                text_segments.append(" ")
            elif content.name not in ['input', 'strong'] or \
                 (content.name == 'strong' and not content.get_text(strip=True).isdigit()):
                text_segments.append(content.get_text(strip=True))
        raw_name_text = " ".join(filter(None, text_segments))
    
    raw_name_text = re.sub(r'\s*-\s*[A-Za-z\s.]+\s*-\s*[RLrl]\s*(must\s*start|sta\.?)\s*$', '', raw_name_text, flags=re.IGNORECASE).strip()
    raw_name_text = re.sub(r'\s*[A-Z]\.\s*[A-Za-z\s.]+\s*-\s*[RLrl]\s*(must\s*start|sta\.?)\s*$', '', raw_name_text, flags=re.IGNORECASE).strip()
    raw_name_text = re.sub(r'^\d{3,7}\s*', '', raw_name_text).strip()
    raw_name_text = re.sub(r'\s*\((hits\+runs\+errors|h\+r\+e|hre)\)$', '', raw_name_text, flags=re.IGNORECASE).strip()
    return " ".join(raw_name_text.split()) if raw_name_text else ""

def american_to_decimal(american_odds_str):
    if american_odds_str is None: return None
    try:
        if isinstance(american_odds_str, str) and not re.match(r"^[+-]?\d+$", american_odds_str.strip()): return None
        odds = float(str(american_odds_str).strip())
        if odds > 0: return (odds / 100.0) + 1.0
        if odds < 0: return (100.0 / abs(odds)) + 1.0
        return None 
    except ValueError: return None

def decimal_to_american(decimal_odds):
    if decimal_odds is None or not isinstance(decimal_odds, (float, int)): return None
    if decimal_odds <= 1.0001: return None 
    if decimal_odds >= 2.0: return f"+{int(round((decimal_odds - 1) * 100))}"
    return f"{int(round(-100 / (decimal_odds - 1)))}"

def adjust_power_probabilities(probabilities, tolerance=1e-4, max_iterations=100):
    k = 1.0 
    valid_probs_for_power = [p for p in probabilities if p is not None and p > 0]
    if not valid_probs_for_power or len(valid_probs_for_power) < 2:
        return [0] * len(valid_probs_for_power)

    for i in range(max_iterations):
        current_powered_probs = []
        for p_val in valid_probs_for_power:
            try:
                current_powered_probs.append(math.pow(p_val, k))
            except ValueError: 
                sum_original_probs = sum(valid_probs_for_power)
                if sum_original_probs == 0: return [0] * len(valid_probs_for_power)
                return [p/sum_original_probs for p in valid_probs_for_power]

        sum_powered_probs = sum(current_powered_probs)
        if sum_powered_probs == 0: break

        overround_metric = sum_powered_probs - 1.0
        if abs(overround_metric) < tolerance: break

        derivative_terms = []
        for p_val in valid_probs_for_power:
            try:
                derivative_terms.append(math.pow(p_val, k) * math.log(p_val))
            except ValueError:
                derivative_terms.append(0) 

        derivative = sum(derivative_terms)
        if abs(derivative) < 1e-9: break 
        k -= overround_metric / derivative

    final_powered_probs = [math.pow(p, k) for p in valid_probs_for_power]
    sum_final_powered_probs = sum(final_powered_probs)

    if sum_final_powered_probs == 0:
        return [1.0 / len(valid_probs_for_power) if valid_probs_for_power else 0] * len(valid_probs_for_power)

    normalized_true_probs = [p_pow / sum_final_powered_probs for p_pow in final_powered_probs]
    return normalized_true_probs

def calculate_nvp_for_market(odds_list):
    valid_odds_indices = [i for i, odd in enumerate(odds_list) if odd is not None and isinstance(odd, (int, float)) and odd > 1.0001]
    if len(valid_odds_indices) < 2: return [None] * len(odds_list)

    current_valid_odds = [odds_list[i] for i in valid_odds_indices]
    implied_probs = []
    for odd in current_valid_odds:
        if odd == 0: return [None] * len(odds_list)
        implied_probs.append(1.0 / odd)

    if sum(implied_probs) == 0 : return [None] * len(odds_list)

    if sum(implied_probs) <= 1.0001 : 
        nvps_for_valid = current_valid_odds
    else:
        true_probs = adjust_power_probabilities(implied_probs)
        nvps_for_valid = [round(1.0 / p, 3) if p is not None and p > 1e-9 else None for p in true_probs]

    final_nvp_list = [None] * len(odds_list)
    for i, original_idx in enumerate(valid_odds_indices):
        if i < len(nvps_for_valid):
          final_nvp_list[original_idx] = nvps_for_valid[i]
    return final_nvp_list

def process_event_odds_for_display(pinnacle_event_json_data):
    """
    Adds NVP (No Vig Price) and American Odds to Pinnacle odds data.
    Modifies the input dictionary in place.
    """
    if not pinnacle_event_json_data or 'data' not in pinnacle_event_json_data:
        return pinnacle_event_json_data

    event_detail = pinnacle_event_json_data['data']
    if not isinstance(event_detail, dict): return pinnacle_event_json_data
    periods = event_detail.get("periods", {})
    if not isinstance(periods, dict): return pinnacle_event_json_data

    for period_key, period_data in periods.items():
        if not isinstance(period_data, dict): continue

        # Remove the 'history' key from each period
        if 'history' in period_data:
            del period_data['history']
            print(f"[DEBUG] History removed for period: {period_key}")

        # Moneyline
        if period_data.get("money_line") and isinstance(period_data["money_line"], dict):
            ml = period_data["money_line"]
            odds_dec = [ml.get("home"), ml.get("draw"), ml.get("away")]
            nvps_dec = calculate_nvp_for_market(odds_dec)

            if len(nvps_dec) == 3:
                ml["nvp_home"] = nvps_dec[0]
                ml["nvp_draw"] = nvps_dec[1]
                ml["nvp_away"] = nvps_dec[2]
            ml["american_home"] = decimal_to_american(ml.get("home"))
            ml["american_draw"] = decimal_to_american(ml.get("draw"))
            ml["american_away"] = decimal_to_american(ml.get("away"))
            ml["nvp_american_home"] = decimal_to_american(ml.get("nvp_home"))
            ml["nvp_american_draw"] = decimal_to_american(ml.get("nvp_draw"))
            ml["nvp_american_away"] = decimal_to_american(ml.get("nvp_away"))

        # Spreads
        if period_data.get("spreads") and isinstance(period_data["spreads"], dict):
            for hdp_key, spread_details in period_data["spreads"].items():
                if isinstance(spread_details, dict):
                    odds_dec = [spread_details.get("home"), spread_details.get("away")]
                    nvps_dec = calculate_nvp_for_market(odds_dec)
                    if len(nvps_dec) == 2:
                        spread_details["nvp_home"], spread_details["nvp_away"] = nvps_dec[0], nvps_dec[1]
                    spread_details["american_home"] = decimal_to_american(spread_details.get("home"))
                    spread_details["american_away"] = decimal_to_american(spread_details.get("away"))
                    spread_details["nvp_american_home"] = decimal_to_american(spread_details.get("nvp_home"))
                    spread_details["nvp_american_away"] = decimal_to_american(spread_details.get("nvp_away"))

        # Totals
        if period_data.get("totals") and isinstance(period_data["totals"], dict):
            for points_key, total_details in period_data["totals"].items():
                if isinstance(total_details, dict):
                    odds_dec = [total_details.get("over"), total_details.get("under")]
                    nvps_dec = calculate_nvp_for_market(odds_dec)
                    if len(nvps_dec) == 2:
                        total_details["nvp_over"], total_details["nvp_under"] = nvps_dec[0], nvps_dec[1]
                    total_details["american_over"] = decimal_to_american(total_details.get("over"))
                    total_details["american_under"] = decimal_to_american(total_details.get("under"))
                    total_details["nvp_american_over"] = decimal_to_american(total_details.get("nvp_over"))
                    total_details["nvp_american_under"] = decimal_to_american(total_details.get("nvp_under"))
    return pinnacle_event_json_data