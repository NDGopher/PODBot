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

    function setStatus(state, message) {
        statusIndicator.className = `status-${state}`;
        statusText.textContent = message;
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
        let card = document.getElementById(`event-${eventId}`);
        if (!card) {
            card = cardTemplate.content.cloneNode(true).querySelector('.event-container');
            card.id = `event-${eventId}`;
            oddsDisplayArea.appendChild(card);
        }

        // Update header info
        card.querySelector('.event-title').textContent = eventData.title;
        card.querySelector('.event-meta-info').textContent = eventData.meta_info;
        card.querySelector('.event-last-update').textContent = `Odds Updated: ${timeSince(eventData.last_update)}`;
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
        let hasPositiveEV = false;
        let markets = eventData.markets && Array.isArray(eventData.markets) ? [...eventData.markets] : [];
        // Sorting support
        if (card.sortByEvDesc === undefined) card.sortByEvDesc = true;
        if (markets.length > 1 && card.sortedByEv) {
            markets.sort((a, b) => {
                const evA = parseFloat(a.ev) || -Infinity;
                const evB = parseFloat(b.ev) || -Infinity;
                return card.sortByEvDesc ? evB - evA : evA - evB;
            });
        }
        markets.forEach(market => {
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
            // Pinnacle NVP cell
            const pinnacleCell = document.createElement('td');
            pinnacleCell.textContent = market.pinnacle_nvp || 'N/A';
            row.appendChild(pinnacleCell);
            // BetBCK odds cell
            const betbckCell = document.createElement('td');
            betbckCell.textContent = market.betbck_odds || 'N/A';
            row.appendChild(betbckCell);
            // EV cell with star for positive EV
            const evCell = document.createElement('td');
            evCell.textContent = market.ev || 'N/A';
            if (market.ev && market.ev !== 'N/A' && parseFloat(market.ev) > 0) {
                evCell.classList.add('positive-ev');
                evCell.innerHTML = `<span style="color:gold; font-size:1.2em; margin-right:4px;">★</span>${market.ev}`;
                hasPositiveEV = true;
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
        // Auto-dismiss after 1 minute if no positive EV
        if (!hasPositiveEV) {
            setTimeout(() => {
                if (document.body.contains(card)) {
                    card.classList.add('dismissed');
                    setTimeout(() => card.remove(), 500);
                }
            }, 60000);
        }
        // Add dismiss button functionality
        const dismissBtn = card.querySelector('.btn-dismiss');
        if (dismissBtn) {
            dismissBtn.onclick = () => {
                dismissedEventIds.add(eventId);
                localStorage.setItem('dismissedEventIds', JSON.stringify(Array.from(dismissedEventIds)));
                card.classList.add('dismissed');
                setTimeout(() => card.remove(), 500);
            };
        }
    }

    function sortCardsByEv() {
        const cards = [...oddsDisplayArea.querySelectorAll('.event-container:not(.dismissed)')];
        cards.sort((a, b) => {
            const evA = parseFloat(a.dataset.maxEv) || -Infinity;
            const evB = parseFloat(b.dataset.maxEv) || -Infinity;
            return evB - evA;
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

            if (currentSignature === lastDataSignature) {
                setStatus('connected', 'Live (No Changes)');
                return;
            }
            
            lastDataSignature = currentSignature;
            setStatus('connected', 'Live (Updated)');
            
            // Show/hide loading message
            if (mainLoadingMessage) {
                mainLoadingMessage.style.display = Object.keys(eventsData).length === 0 ? 'block' : 'none';
            }

            // Remove expired cards
            const receivedEventIds = new Set(Object.keys(eventsData));
            [...oddsDisplayArea.children].forEach(card => {
                const eventId = card.id?.replace('event-', '');
                if (eventId && !receivedEventIds.has(eventId)) {
                    card.classList.add('dismissed');
                    setTimeout(() => card.remove(), 500);
                }
            });

            // Create/update cards for each event
            for (const [eventId, eventData] of Object.entries(eventsData)) {
                createOrUpdateEventCard(eventId, eventData);
            }

        } catch (error) {
            console.error("Error refreshing events:", error);
            setStatus('disconnected', 'Connection Error');
        }
    }
    
    // Initial fetch and start refresh interval
    fetchAndRefresh();
    setInterval(fetchAndRefresh, REFRESH_INTERVAL_MS);
});