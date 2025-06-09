document.addEventListener('DOMContentLoaded', () => {
    const oddsDisplayArea = document.getElementById("oddsDisplayArea");
    const mainLoadingMessage = document.getElementById("mainLoadingMessage");
    const cardTemplate = document.getElementById("event-card-template");
    const statusIndicator = document.getElementById('status-indicator');
    const statusText = document.getElementById('status-text');

    if (!oddsDisplayArea || !cardTemplate || !statusIndicator) {
        console.error("Realtime.js: Critical element missing!");
        return;
    }
    console.log("Realtime.js v12.0 (Fixed Data Display) Loaded.");

    const REFRESH_INTERVAL_MS = 3000;
    const POSITIVE_EV_THRESHOLD = 0.0001; // 0.01%
    const NO_EV_TIMEOUT_MS = 60000; // 1 minute
    const DISMISSAL_TIMEOUT_MS = 180000; // 3 minutes
    let lastDataSignature = "";
    let cardTimeouts = new Map();
    let eventTimeouts = {};

    if (!window.openedEvPopups) {
        window.openedEvPopups = {};
    }

    // Track dismissed event IDs
    let dismissedEventIds = new Set(JSON.parse(localStorage.getItem('dismissedEventIds') || '[]'));
    // Track which eventIds are currently visible (not dismissed)
    let visibleEventIds = new Set();

    // Track previous odds for flashing
    let previousOdds = {};

    function setStatus(state, message) {
        statusIndicator.className = `status-${state}`;
        statusText.textContent = message;
    }

    function getArrow(newVal, oldVal) {
        if (newVal == null || oldVal == null || newVal === oldVal) return '';
        if (parseFloat(newVal) > parseFloat(oldVal)) return '↑';
        if (parseFloat(newVal) < parseFloat(oldVal)) return '↓';
        return '';
    }

    function timeSince(timestamp) {
        if (!timestamp) return 'N/A';
        const seconds = Math.floor((new Date() - new Date(timestamp * 1000)) / 1000);
        if (seconds < 5) return "just now";
        let interval = seconds / 31536000;
        if (interval > 1) return Math.floor(interval) + " years ago";
        interval = seconds / 2592000;
        if (interval > 1) return Math.floor(interval) + " months ago";
        interval = seconds / 86400;
        if (interval > 1) return Math.floor(interval) + " days ago";
        interval = seconds / 3600;
        if (interval > 1) return Math.floor(interval) + "h ago";
        interval = seconds / 60;
        if (interval > 1) return Math.floor(interval) + "m ago";
        return Math.floor(seconds) + "s ago";
    }
    
    function americanToDecimal(americanOdds) {
        if (americanOdds === null || americanOdds === undefined) return null;
        const odds = parseFloat(americanOdds);
        if (isNaN(odds)) return null;
        if (odds > 0) return (odds / 100) + 1;
        if (odds < 0) return (100 / Math.abs(odds)) + 1;
        return null;
    }

    function showPositiveEvPopup(eventData, marketDetails) {
        const { eventId, homeTeam, awayTeam, periodName } = eventData;
        const { selectionName, lineDisplay, marketType, bckDisplay, pinNvpDisplay, evDisplay } = marketDetails;
        const popupKey = `evPopup_${eventId}_${marketType}_${selectionName}_${lineDisplay}`.replace(/[^a-zA-Z0-9]/g, '_');

        if (window.openedEvPopups[popupKey] && !window.openedEvPopups[popupKey].closed) {
            window.openedEvPopups[popupKey].focus();
            return;
        }

        const popup = window.open('', popupKey, `width=450,height=350,scrollbars=yes,resizable=yes`);
        if (!popup) {
            console.warn("Popup blocked by browser.");
            return;
        }
        window.openedEvPopups[popupKey] = popup;

        function updatePopup() {
            fetch(`/get_active_events_data`, { mode: 'cors' })
                .then(response => response.json())
                .then(data => {
                    const event = data[eventId];
                    if (event) {
                        const market = event.markets.find(m => m.market === marketType && m.selection === selectionName && m.line === lineDisplay);
                        if (market) {
                            popup.document.body.innerHTML = `
                                <style>
                                    body { font-family: system-ui, sans-serif; background-color: #1f2937; color: #f9fafb; padding: 20px; }
                                    h3 { color: #3b82f6; }
                                    p { margin: 8px 0; line-height: 1.5; }
                                    strong { color: #9ca3af; }
                                    .ev-value { color: #22c55e; font-weight: bold; font-size: 1.2em; }
                                </style>
                                <h3>Positive EV Opportunity!</h3>
                                <p><strong>Event:</strong> ${homeTeam} vs ${awayTeam}</p>
                                <p><strong>Period:</strong> ${periodName}</p>
                                <hr>
                                <p><strong>Market:</strong> ${marketType}</p>
                                <p><strong>Selection:</strong> ${selectionName} ${lineDisplay}</p>
                                <p><strong>BetBCK Odds:</strong> ${market.betbck_odds || 'N/A'}</p>
                                <p><strong>Pinnacle NVP:</strong> ${market.pinnacle_nvp || 'N/A'}</p>
                                <p class="ev-value">EV: ${market.ev || 'N/A'}</p>
                            `;
                        }
                    }
                })
                .catch(() => popup.close());
        }

        popup.document.title = `+EV Alert: ${selectionName}`;
        updatePopup();
        setInterval(updatePopup, REFRESH_INTERVAL_MS);
    }

    function cleanTeamName(name, eventTitle) {
        // Use the event title to extract team names
        if (!name) return '';
        // Try to match the team name from the event title
        if (eventTitle) {
            const teams = eventTitle.split(' vs ');
            for (const t of teams) {
                if (t && name.toLowerCase().includes(t.toLowerCase().replace(/[^a-zA-Z0-9 ]/g, ''))) {
                    return t.trim();
                }
            }
        }
        // Remove common suffixes
        return name.replace(/(MLB|NBA|NFL|NHL|NCAAF|NCAAB|FIFA)$/i, '').trim();
    }

    // Helper to get league emoji
    function getLeagueEmoji(metaInfo) {
        if (!metaInfo) return '';
        const league = metaInfo.toLowerCase();
        if (league.includes('mlb')) return '⚾';
        if (league.includes('nba')) return '🏀';
        if (league.includes('nhl') || league.includes('hockey')) return '🏒';
        if (league.includes('soccer') || league.includes('fifa') || league.includes('football')) return '⚽';
        if (league.includes('nfl')) return '🏈';
        return '';
    }

    // Helper to check if a market is positive or zero EV
    function isPositiveOrZeroEV(ev) {
        const val = parseFloat(ev);
        return !isNaN(val) && val >= 0;
    }

    function renderRow(market) {
        const row = document.createElement('tr');
        
        // Market type cell
        const marketCell = document.createElement('td');
        marketCell.textContent = market.market;
        row.appendChild(marketCell);
        
        // Selection cell
        const selectionCell = document.createElement('td');
        selectionCell.textContent = market.selection;
        row.appendChild(selectionCell);
        
        // Line cell
        const lineCell = document.createElement('td');
        lineCell.textContent = market.line || '';
        row.appendChild(lineCell);
        
        // Pinnacle odds cell
        const pinnacleCell = document.createElement('td');
        pinnacleCell.textContent = market.pinnacle_odds || '';
        row.appendChild(pinnacleCell);
        
        // BetBCK odds cell
        const betbckCell = document.createElement('td');
        betbckCell.textContent = market.betbck_odds || '';
        row.appendChild(betbckCell);
        
        // EV cell
        const evCell = document.createElement('td');
        evCell.textContent = market.ev || 'N/A';
        if (market.ev && parseFloat(market.ev) > 0) {
            evCell.classList.add('positive-ev');
        }
        row.appendChild(evCell);
        
        return row;
    }

    function createOrUpdateEventCard(eventId, eventData) {
        if (dismissedEventIds.has(eventId)) return; // Don't render dismissed cards
        visibleEventIds.add(eventId);
        let card = document.getElementById(`event-${eventId}`);
        if (!card) {
            card = cardTemplate.content.cloneNode(true).querySelector('.event-container');
            card.id = `event-${eventId}`;
            oddsDisplayArea.appendChild(card);
        }

        // Update header info
        const leagueEmoji = getLeagueEmoji(eventData.meta_info);
        card.querySelector('.event-title').textContent = `${leagueEmoji ? leagueEmoji + ' ' : ''}${eventData.title}`;
        card.querySelector('.event-meta-info').textContent = eventData.meta_info;
        card.querySelector('.event-last-update').textContent = `Odds Updated: ${timeSince(eventData.last_update)}`;
        // Show BetBCK refreshed timer
        let betbckTimer = card.querySelector('.betbck-last-update');
        if (!betbckTimer) {
            betbckTimer = document.createElement('p');
            betbckTimer.className = 'betbck-last-update';
            card.querySelector('.event-header-info').appendChild(betbckTimer);
        }
        betbckTimer.textContent = `BetBCK Refreshed: ${timeSince(eventData.betbck_last_update)}`;
        card.querySelector('.event-time-since').textContent = `Alert ${timeSince(eventData.alert_arrival_timestamp)}`;

        // Update alert info
        card.querySelector('.alert-description').textContent = eventData.alert_description;
        card.querySelector('.alert-meta').textContent = eventData.alert_meta;

        // Remove BetBCK status line
        const betbckStatusContainer = card.querySelector('.betbck-status-container');
        betbckStatusContainer.textContent = '';
        betbckStatusContainer.style.display = 'none';

        // Update markets table
        const tbody = card.querySelector('tbody');
        tbody.innerHTML = '';
        let hasPositiveOrZeroEV = false;
        let markets = eventData.markets && Array.isArray(eventData.markets) ? [...eventData.markets] : [];
        // Auto-sort by EV descending by default, treating 0% as positive
        markets.sort((a, b) => {
            const evA = parseFloat(a.ev);
            const evB = parseFloat(b.ev);
            if (isNaN(evA) && isNaN(evB)) return 0;
            if (isNaN(evA)) return 1;
            if (isNaN(evB)) return -1;
            // 0% is better than negative
            if (evA >= 0 && evB < 0) return -1;
            if (evA < 0 && evB >= 0) return 1;
            return evB - evA;
        });
        card.sortedByEv = true;
        card.sortByEvDesc = true;
        // Track previous odds for flashing
        if (!previousOdds[eventId]) previousOdds[eventId] = {};
        markets.forEach((market, idx) => {
            if (!market.betbck_odds || market.betbck_odds === 'N/A') return; // Only show rows with BetBCK odds
            const row = document.createElement('tr');
            // Market cell
            const marketCell = document.createElement('td');
            marketCell.textContent = market.market;
            row.appendChild(marketCell);
            // Selection cell (cleaned)
            const selectionCell = document.createElement('td');
            selectionCell.textContent = cleanTeamName(market.selection, eventData.title);
            row.appendChild(selectionCell);
            // Line cell
            const lineCell = document.createElement('td');
            lineCell.textContent = market.line || '';
            row.appendChild(lineCell);
            // Pinnacle NVP cell with flash/arrow
            const pinnacleCell = document.createElement('td');
            let prevPin = previousOdds[eventId][`pin_${idx}`];
            let arrowPin = getArrow(market.pinnacle_nvp, prevPin);
            pinnacleCell.textContent = market.pinnacle_nvp || 'N/A';
            if (arrowPin) pinnacleCell.innerHTML += ` <span style='font-size:1.1em;'>${arrowPin}</span>`;
            if (prevPin !== undefined && market.pinnacle_nvp !== prevPin) {
                pinnacleCell.classList.add('flash-yellow');
                setTimeout(() => pinnacleCell.classList.remove('flash-yellow'), 2000);
            }
            previousOdds[eventId][`pin_${idx}`] = market.pinnacle_nvp;
            row.appendChild(pinnacleCell);
            // BetBCK odds cell with flash/arrow
            const betbckCell = document.createElement('td');
            let prevBck = previousOdds[eventId][`bck_${idx}`];
            let arrowBck = getArrow(market.betbck_odds, prevBck);
            betbckCell.textContent = market.betbck_odds || 'N/A';
            if (arrowBck) betbckCell.innerHTML += ` <span style='font-size:1.1em;'>${arrowBck}</span>`;
            if (prevBck !== undefined && market.betbck_odds !== prevBck) {
                betbckCell.classList.add('odds-flash');
                setTimeout(() => betbckCell.classList.remove('odds-flash'), 800);
            }
            previousOdds[eventId][`bck_${idx}`] = market.betbck_odds;
            row.appendChild(betbckCell);
            // EV cell with star for positive/zero EV
            const evCell = document.createElement('td');
            evCell.textContent = market.ev || 'N/A';
            if (market.ev && market.ev !== 'N/A' && parseFloat(market.ev) >= 0) {
                evCell.classList.add('positive-ev');
                evCell.innerHTML = `<span style=\"color:gold; font-size:1.2em; margin-right:4px;\">★</span>${market.ev}`;
                hasPositiveOrZeroEV = true;
            }
            row.appendChild(evCell);
            tbody.appendChild(row);
        });
        // Add sorting by EV on header click
        const table = card.querySelector('table');
        const evHeader = table.querySelector('th.col-ev');
        if (evHeader && !evHeader.hasSortListener) {
            evHeader.style.cursor = 'pointer';
            evHeader.title = 'Sort by EV';
            evHeader.addEventListener('click', () => {
                card.sortedByEv = true;
                card.sortByEvDesc = !card.sortByEvDesc;
                createOrUpdateEventCard(eventId, eventData);
            });
            evHeader.hasSortListener = true;
        }
        // Auto-dismiss logic
        if (!card.firstNoEvTimestamp) card.firstNoEvTimestamp = null;
        if (card.dismissTimeout) clearTimeout(card.dismissTimeout);
        if (card.betbckRefreshTimeout) clearTimeout(card.betbckRefreshTimeout);
        if (hasPositiveOrZeroEV) {
            // Refresh BetBCK odds after 1 minute ONLY if card is still visible
            card.betbckRefreshTimeout = setTimeout(() => {
                if (visibleEventIds.has(eventId)) fetchAndRefresh();
            }, 60000);
            // Dismiss after 3 minutes
            card.dismissTimeout = setTimeout(autoDismissCard, 180000);
            card.firstNoEvTimestamp = null;
        } else {
            // Track first time with no positive/zero EV
            if (!card.firstNoEvTimestamp) card.firstNoEvTimestamp = Date.now();
            // Dismiss after 1 minute from first no-EV
            const msSinceNoEv = Date.now() - card.firstNoEvTimestamp;
            const msLeft = Math.max(60000 - msSinceNoEv, 0);
            card.dismissTimeout = setTimeout(autoDismissCard, msLeft);
        }
        // Add dismiss button functionality
        const dismissBtn = card.querySelector('.btn-dismiss');
        if (dismissBtn) {
            dismissBtn.onclick = () => {
                dismissedEventIds.add(eventId);
                localStorage.setItem('dismissedEventIds', JSON.stringify(Array.from(dismissedEventIds)));
                card.classList.add('dismissed');
                setTimeout(() => card.remove(), 500);
                visibleEventIds.delete(eventId);
            };
        }
    }

    // Sort event cards: +EV or 0% EV cards at the top, then by most recent alert
    function sortEventCardsByEvAndAlertTime() {
        const cards = [...oddsDisplayArea.querySelectorAll('.event-container:not(.dismissed)')];
        cards.sort((a, b) => {
            // +EV or 0% at top
            const aHasPosEv = !!a.querySelector('.positive-ev');
            const bHasPosEv = !!b.querySelector('.positive-ev');
            if (aHasPosEv !== bHasPosEv) return bHasPosEv - aHasPosEv;
            // Then by alert time (descending)
            const aTime = parseFloat(a.querySelector('.event-time-since').getAttribute('data-timestamp')) || 0;
            const bTime = parseFloat(b.querySelector('.event-time-since').getAttribute('data-timestamp')) || 0;
            return bTime - aTime;
        });
        cards.forEach(card => oddsDisplayArea.appendChild(card));
    }

    async function fetchAndRefresh() {
        try {
            const response = await fetch('/get_active_events_data', { mode: 'cors' });
            if (!response.ok) throw new Error(`HTTP error ${response.status}: ${await response.text()}`);
            const eventsData = await response.json();
            const currentSignature = JSON.stringify(eventsData);
            // Remove dismissed IDs that are no longer in the feed (so new alerts can show up)
            for (const eventId of Array.from(dismissedEventIds)) {
                if (!(eventId in eventsData)) {
                    dismissedEventIds.delete(eventId);
                }
            }
            localStorage.setItem('dismissedEventIds', JSON.stringify(Array.from(dismissedEventIds)));
            visibleEventIds.clear();
            if (currentSignature === lastDataSignature) {
                setStatus('connected', 'Live (No Changes)');
                return;
            }
            lastDataSignature = currentSignature;
            setStatus('connected', 'Live (Updated)');
            if (mainLoadingMessage) {
                mainLoadingMessage.style.display = Object.keys(eventsData).length === 0 ? 'block' : 'none';
            }
            const receivedEventIds = new Set(Object.keys(eventsData));
            [...oddsDisplayArea.children].forEach(card => {
                const eventId = card.id?.replace('event-', '');
                if (eventId && !receivedEventIds.has(eventId)) {
                    card.classList.add('dismissed');
                    setTimeout(() => card.remove(), 500);
                    visibleEventIds.delete(eventId);
                }
            });
            // Create/update cards for each event
            // Sort by +EV or 0% EV, then most recent alert
            const sortedEntries = Object.entries(eventsData).sort(([, a], [, b]) => {
                // +EV or 0% at top
                const aHasPosEv = (a.markets || []).some(m => parseFloat(m.ev) >= 0);
                const bHasPosEv = (b.markets || []).some(m => parseFloat(m.ev) >= 0);
                if (aHasPosEv !== bHasPosEv) return bHasPosEv - aHasPosEv;
                // Then by alert time (descending)
                return (b.alert_arrival_timestamp || 0) - (a.alert_arrival_timestamp || 0);
            });
            for (const [eventId, eventData] of sortedEntries) {
                createOrUpdateEventCard(eventId, eventData);
            }
            // Sort event cards in DOM
            sortEventCardsByEvAndAlertTime();
        } catch (error) {
            console.error("[Realtime.js] Error refreshing:", error);
            if (mainLoadingMessage) mainLoadingMessage.textContent = `Error: ${error.message}`;
        }
    }
    
    // Initial fetch and start refresh interval
    fetchAndRefresh();
    setInterval(fetchAndRefresh, REFRESH_INTERVAL_MS);

    function dismissEventBackend(eventId) {
        fetch('/dismiss_event', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ eventId })
        }).catch(() => {});
    }

    function autoDismissCard() {
        // 'this' should be bound to the card element
        const card = this;
        const eventId = card.id?.replace('event-', '');
        if (!eventId) return;
        dismissedEventIds.add(eventId);
        localStorage.setItem('dismissedEventIds', JSON.stringify(Array.from(dismissedEventIds)));
        card.classList.add('dismissed');
        setTimeout(() => card.remove(), 500);
        visibleEventIds.delete(eventId);
    }
});