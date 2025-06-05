import requests
from bs4 import BeautifulSoup
import os
from datetime import datetime
import brotli
import re

# URLs for betbck.com
LOGIN_URL = 'https://betbck.com/Qubic/SecurityPage.php'
SELECTION_URL = 'https://betbck.com/Qubic/StraightLoginSportSelection.php'
STRAIGHT_GAMES_URL = 'https://betbck.com/Qubic/PlayerGameSelection.php'

# Login credentials (replace with your actual ones)
PAYLOAD = {
    'customerID': 'xyz005',  # Update with your actual customerID
    'password': 'xyz005',    # Update with your actual password
    'B1.x': '40',
    'B1.y': '6'
}

# Headers
HEADERS = {
    'Host': 'betbck.com',
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
    'Accept-Encoding': 'gzip, deflate, br, zstd',
    'Accept-Language': 'en-US,en;q=0.9',
    'Content-Type': 'application/x-www-form-urlencoded',
    'Origin': 'https://betbck.com',
    'Referer': 'https://betbck.com/Qubic/StraightLoginSportSelection.php',
    'Connection': 'keep-alive',
    'DNT': '1',
    'Upgrade-Insecure-Requests': '1',
    'Sec-Fetch-Dest': 'document',
    'Sec-Fetch-Mode': 'navigate',
    'Sec-Fetch-Site': 'same-origin',
    'Sec-Fetch-User': '?1',
    'Sec-CH-UA': '"Not A(Brand";v="8", "Chromium";v="132", "Google Chrome";v="132"',
    'Sec-CH-UA-Mobile': '?0',
    'Sec-CH-UA-Platform': '"Windows"',
    'Pragma': 'no-cache',
    'Cache-Control': 'no-cache'
}

# Headers for Soccerway verification
SOCCERWAY_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
}

LEAGUE_NAMES = {}

def parse_datetime(date_str):
    """Parse the date string (e.g., 'Wed 2/26 02:00PM') into a datetime object."""
    try:
        date_str = date_str.replace('\xa0', ' ').replace('  ', ' ').strip()
        return datetime.strptime(date_str, '%a %m/%d %I:%M%p')
    except ValueError as e:
        print(f"Error parsing date {date_str}: {e}")
        return None

def verify_home_away(home_team, away_team, game_date, league):
    """Verify home/away teams against Soccerway.com."""
    try:
        # Convert game_date to YYYY-MM-DD for Soccerway URL
        dt = parse_datetime(game_date)
        if not dt:
            print(f"Cannot verify {home_team} vs {away_team}: Invalid date")
            return home_team, away_team  # Fallback to original if date parsing fails

        date_str = dt.strftime('%Y-%m-%d')
        soccerway_url = f"https://us.soccerway.com/matches/{date_str}/"
        response = requests.get(soccerway_url, headers=SOCCERWAY_HEADERS)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Find match block
        matches = soup.find_all('tr', class_='match')
        for match in matches:
            teams = match.find_all('td', class_=['team-a', 'team-b'])
            if len(teams) == 2:
                soccerway_home = teams[0].get_text(strip=True).lower()
                soccerway_away = teams[1].get_text(strip=True).lower()
                html_home = home_team.lower()
                html_away = away_team.lower()
                # Fuzzy match (partial string match due to naming variations)
                if (html_home in soccerway_home or soccerway_home in html_home) and \
                   (html_away in soccerway_away or soccerway_away in html_away):
                    print(f"Verified: Soccerway lists {teams[0].get_text(strip=True)} (Home) vs {teams[1].get_text(strip=True)} (Away)")
                    return teams[0].get_text(strip=True), teams[1].get_text(strip=True)
                elif (html_home in soccerway_away or soccerway_away in html_home) and \
                     (html_away in soccerway_home or soccerway_home in html_away):
                    print(f"Swapped: Soccerway lists {teams[0].get_text(strip=True)} (Home) vs {teams[1].get_text(strip=True)} (Away), HTML had {home_team} (Home) vs {away_team} (Away)")
                    return teams[0].get_text(strip=True), teams[1].get_text(strip=True)
        print(f"Warning: No Soccerway match found for {home_team} vs {away_team}, using HTML order")
        return home_team, away_team  # Fallback if no match found
    except Exception as e:
        print(f"Error verifying {home_team} vs {away_team} on Soccerway: {e}")
        return home_team, away_team  # Fallback to original on error

def parse_odds_table(table, home_team, away_team, game_date, league, period):
    """Parse odds, ensuring correct home/away assignment after verification."""
    odds_data = {
        'Home Team': home_team.strip() or 'N/A',
        'Away Team': away_team.strip() or 'N/A',
        'Home Spread': 'N/A', 'Away Spread': 'N/A',
        'Home ML': 'N/A', 'Away ML': 'N/A',
        'Game Over': 'N/A', 'Game Under': 'N/A',
        'Home TT Over': 'N/A', 'Home TT Under': 'N/A',
        'Away TT Over': 'N/A', 'Away TT Under': 'N/A',
        'Date': game_date,
        'League': league,
        'Period': period
    }

    rows = table.find_all('tr')
    if len(rows) < 2:
        print(f"Warning: Insufficient rows ({len(rows)}) for {home_team} vs {away_team}, Period: {period}")
        return odds_data

    # Parse home team odds (row 0)
    home_tds = rows[0].find_all('td', class_='tbl_betAmount_td')
    for td in home_tds:
        title = td.find('span', class_='type_title')
        if title:
            bet_type = title.get_text(strip=True)
            odds = td.get_text(strip=True).replace(bet_type, '').replace('\xa0', ' ').strip()
            if odds:
                if 'Spread' in bet_type:
                    odds_data['Home Spread'] = odds
                elif 'Money Line' in bet_type:
                    odds_data['Home ML'] = odds
                elif 'Total' in bet_type and 'o' in odds.lower() and odds_data['Game Over'] == 'N/A':
                    odds_data['Game Over'] = odds
                elif 'Team Total' in bet_type and 'o' in odds.lower():
                    odds_data['Home TT Over'] = odds
                elif 'Team Total' in bet_type and 'u' in odds.lower():
                    odds_data['Home TT Under'] = odds

    # Parse away team odds (row 1)
    away_tds = rows[1].find_all('td', class_='tbl_betAmount_td')
    if len(away_tds) >= 5:
        for i, td in enumerate(away_tds):
            odds = td.get_text(strip=True).replace('\xa0', ' ').strip()
            if odds:
                title = td.find('span', class_='type_title')
                bet_type = title.get_text(strip=True) if title else ''
                if i == 0 or 'Spread' in bet_type:
                    odds_data['Away Spread'] = odds
                elif i == 1 or 'Money Line' in bet_type:
                    odds_data['Away ML'] = odds
                elif i == 2 or ('Total' in bet_type and 'u' in odds.lower() and odds_data['Game Under'] == 'N/A'):
                    odds_data['Game Under'] = odds
                elif i == 3 or ('Team Total' in bet_type and 'o' in odds.lower()):
                    odds_data['Away TT Over'] = odds
                elif i == 4 or ('Team Total' in bet_type and 'u' in odds.lower()):
                    odds_data['Away TT Under'] = odds

    return odds_data

def fetch_1st_half_odds(session, game_num, home_team, away_team, game_date, league):
    """Fetch and parse 1st Half odds."""
    try:
        first_half_url = f"https://betbck.com/Qubic/GamePeriodsAjax.php?gameNum={game_num}&periods=1st+Half"
        response = session.get(first_half_url, headers=HEADERS)
        response.raise_for_status()
        first_half_soup = BeautifulSoup(response.text, 'html.parser')
        first_half_table = first_half_soup.find('table', class_='new_tb_cont')
        if first_half_table:
            return parse_odds_table(first_half_table, home_team, away_team, game_date, league, '1st Half')
        return None
    except Exception as e:
        print(f"Error fetching 1st Half odds for {home_team} vs {away_team}: {e}")
        return None

def scrape_betbck_odds():
    try:
        with requests.Session() as session:
            # Log in
            login_response = session.post(LOGIN_URL, data=PAYLOAD)
            login_response.raise_for_status()
            HEADERS['Cookie'] = '; '.join([f"{k}={v}" for k, v in session.cookies.get_dict().items()])

            # Scrape league selection page
            selection_response = session.get(SELECTION_URL, headers=HEADERS)
            selection_response.raise_for_status()
            selection_soup = BeautifulSoup(selection_response.text, 'html.parser')
            soccer_inputs = selection_soup.find_all('input', {'name': re.compile(r'SOCCER_.*?Game_')})
            inet_wager_number = selection_soup.find('input', {'name': 'inetWagerNumber'})
            inet_wager_value = inet_wager_number['value'] if inet_wager_number else '0.04767148518361164'

            DYNAMIC_POST_DATA = {
                'x': '112', 'y': '10', 'keyword_search': '', 'inetWagerNumber': inet_wager_value,
                'inetSportSelection': 'sport', 'contestType1': '', 'contestType2': '', 'contestType3': ''
            }
            for input_tag in soccer_inputs:
                league_id = input_tag.get('name')
                league_name = input_tag.find_next('a').get_text(strip=True)
                DYNAMIC_POST_DATA[league_id] = 'on'
                LEAGUE_NAMES[league_id] = league_name

            # Fetch games page
            games_response = session.post(STRAIGHT_GAMES_URL, data=DYNAMIC_POST_DATA, headers=HEADERS, stream=True)
            games_response.raise_for_status()
            content_encoding = games_response.headers.get('content-encoding', '').lower()
            games_text = brotli.decompress(games_response.content).decode('utf-8') if content_encoding == 'br' else games_response.text

            soup = BeautifulSoup(games_text, 'html.parser')
            game_tables = soup.find_all('table', class_='new_tb_cont')
            games_by_league = {}

            for table in game_tables:
                header_table = table.find_previous('table', class_=['teams_betting_options', 'teams_betting_options_2'])
                if header_table:
                    league_date_elem = header_table.find_previous('span', class_='sportName-right')
                    league = league_date_elem.get_text(strip=True) if league_date_elem else "Unknown League"
                    date_elem = header_table.find('div', class_='dateLinebetting')
                    game_date = date_elem.get_text(strip=True).replace('  ', ' ') if date_elem else "Unknown Date"

                    local_team = header_table.find('span', class_='game_number_local')
                    visitor_team = header_table.find('span', class_='game_number_visitor')
                    if local_team and visitor_team:
                        local_name = local_team.find_next('span').get_text(strip=True) if local_team.find_next('span') else local_team.get_text(strip=True).replace('<strong>', '').replace('</strong>', '').strip()
                        visitor_name = visitor_team.find_next('span').get_text(strip=True) if visitor_team.find_next('span') else visitor_team.get_text(strip=True).replace('<strong>', '').replace('</strong>', '').strip()

                        # Verify home/away with Soccerway
                        verified_home, verified_away = verify_home_away(local_name, visitor_name, game_date, league)
                        full_game_odds = parse_odds_table(table, verified_home, verified_away, game_date, league, 'Full Game')
                        if full_game_odds:
                            if league not in games_by_league:
                                games_by_league[league] = []
                            games_by_league[league].append(full_game_odds)

                        first_half_button = table.find('input', {'value': re.compile(r'1st Half|1H', re.I)})
                        if first_half_button and 'onclick' in first_half_button.attrs:
                            match = re.search(r"getPeriods\('([^']+)','1st Half'\)", first_half_button['onclick'])
                            if match:
                                game_num = match.group(1)
                                first_half_odds = fetch_1st_half_odds(session, game_num, verified_home, verified_away, game_date, league)
                                if first_half_odds:
                                    games_by_league[league].append(first_half_odds)

            if games_by_league:
                sorted_games_by_league = {}
                for league in games_by_league:
                    sorted_games = sorted(games_by_league[league], key=lambda x: parse_datetime(x['Date']) if parse_datetime(x['Date']) else datetime.max)
                    sorted_games_by_league[league] = sorted_games

                league_start_times = {league: min([parse_datetime(g['Date']) for g in games if parse_datetime(g['Date'])], default=datetime.max) for league, games in sorted_games_by_league.items()}
                sorted_leagues = sorted(league_start_times.keys(), key=lambda x: league_start_times[x])

                # HTML Output
                html_output = f"""
                <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Daily Soccer Odds for {datetime.now().strftime('%Y-%m-%d')}</title>
                <style>table {{ border-collapse: collapse; width: 100%; margin-bottom: 20px; }} th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }} th {{ background-color: #f2f2f2; }} h2 {{ color: #333; }}</style>
                </head><body><h1>Daily Soccer Odds for {datetime.now().strftime('%Y-%m-%d')}</h1>
                """
                for league in sorted_leagues:
                    html_output += f"<h2>{league}</h2><table><tr><th>League</th><th>Period</th><th>Home Team</th><th>Away Team</th><th>Date</th><th>Home Spread</th><th>Away Spread</th><th>Home ML</th><th>Away ML</th><th>Game Over</th><th>Game Under</th><th>Home TT Over</th><th>Home TT Under</th><th>Away TT Over</th><th>Away TT Under</th></tr>"
                    for game in sorted_games_by_league[league]:
                        html_output += f"<tr><td>{game['League']}</td><td>{game['Period']}</td><td>{game['Home Team']}</td><td>{game['Away Team']}</td><td>{game['Date']}</td><td>{game['Home Spread']}</td><td>{game['Away Spread']}</td><td>{game['Home ML']}</td><td>{game['Away ML']}</td><td>{game['Game Over']}</td><td>{game['Game Under']}</td><td>{game['Home TT Over']}</td><td>{game['Home TT Under']}</td><td>{game['Away TT Over']}</td><td>{game['Away TT Under']}</td></tr>"
                    html_output += "</table>"
                html_output += "</body></html>"

                output_dir = os.path.abspath(os.getcwd())
                html_output_file = os.path.join(output_dir, 'daily_soccer_odds.html')
                with open(html_output_file, 'w', encoding='utf-8') as f:
                    f.write(html_output)
                print(f"HTML Results saved to {html_output_file}")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    scrape_betbck_odds()