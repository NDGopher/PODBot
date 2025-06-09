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
    console.log("Realtime.js v11.0 (Popups & Timestamps) Loaded.");

    const REFRESH_INTERVAL_MS = 3000;
    const POSITIVE_EV_THRESHOLD = 0.0001; // 0.01%
    const NO_EV_TIMEOUT_MS = 60000; // 1 minute
    const DISMISSAL_TIMEOUT_MS = 180000; // 3 minutes
    let lastDataSignature = "";
    let cardTimeouts = new Map();

    if (!window.openedEvPopups) {
        window.openedEvPopups = {};
    }

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

    function createOrUpdateEventCard(eventId, eventData) {
        let card = document.getElementById(`event-${eventId}`);
        const isNewCard = !card;
        const alertTimestamp = eventData.alert_arrival_timestamp;

        if (isNewCard) {
            card = cardTemplate.content.cloneNode(true).firstElementChild;
            card.id = `event-${eventId}`;
        }

        const { title, meta_info, last_update, alert_description, alert_meta, betbck_status, markets } = eventData;
        const [league, start] = meta_info.split(' | ');
        const [homeTeam, awayTeam] = title.split(' vs ');
        const lastUpdateTimestamp = new Date(last_update).getTime() / 1000;

        card.querySelector('.event-title').textContent = `${homeTeam} vs ${awayTeam}`; // Use cleaned team names
        card.querySelector('.event-meta-info').textContent = `${league} | Starts: ${start || 'N/A'}`;
        card.querySelector('.event-last-update').textContent = `Odds Updated: ${timeSince(lastUpdateTimestamp)}`;
        card.querySelector('.event-time-since').textContent = `Alert ${timeSince(alertTimestamp)}`;
        card.querySelector('.alert-description').textContent = alert_description;
        card.querySelector('.alert-meta').textContent = alert_meta;
        card.querySelector('.betbck-status-container').textContent = betbck_status;

        const tableBody = card.querySelector('tbody');
        const prevTableBodyHtml = tableBody.innerHTML;
        tableBody.innerHTML = '';
        let hasPositiveEv = false;
        let maxEv = -Infinity;

        console.log("Markets data:", markets); // Debug log to check data

        const renderRow = (marketType, selectionName, lineDisplay, pinNvpAm, bckOddsAm, evDisplay, periodName) => {
            const pinNvpDisplay = pinNvpAm !== null && pinNvpAm !== undefined ? pinNvpAm : 'N/A';
            const bckDisplay = bckOddsAm !== null && bckOddsAm !== undefined ? bckOddsAm : 'N/A';
            let rowClass = '';

            console.log(`Rendering row: ${marketType}, ${selectionName}, ${lineDisplay}, ${pinNvpDisplay}, ${bckDisplay}, ${evDisplay}`); // Debug log

            if (evDisplay !== 'N/A') {
                const evValue = parseFloat(evDisplay);
                if (evValue > POSITIVE_EV_THRESHOLD) {
                    rowClass = 'positive-ev';
                    hasPositiveEv = true;
                    if (isNewCard) {
                        showPositiveEvPopup(
                            { eventId, homeTeam, awayTeam, periodName },
                            { selectionName, lineDisplay, marketType, bckDisplay, pinNvpDisplay, evDisplay }
                        );
                    }
                }
                maxEv = Math.max(maxEv, evValue);
            }

            const row = document.createElement('tr');
            row.className = rowClass;
            row.innerHTML = `
                <td>${marketType}</td>
                <td>${selectionName}</td>
                <td>${lineDisplay || ''}</td>
                <td class="col-odds">${pinNvpDisplay}</td>
                <td class="col-odds">${bckDisplay}</td>
                <td class="col-ev">${evDisplay}</td>
            `;
            return row;
        };

        markets.forEach(market => {
            const periodName = market.market.includes('1H') ? "1st Half" : "Full Game";
            renderRow(
                market.market.replace(' 1H', ''),
                market.selection,
                market.line,
                market.pinnacle_nvp,
                market.betbck_odds,
                market.ev,
                periodName
            ).forEach(row => tableBody.appendChild(row));
        });

        // Add market group headers manually if needed
        if (markets.some(m => !m.market.includes('1H'))) {
            const fullGameGroup = document.createElement('tr');
            fullGameGroup.className = 'market-group-row';
            fullGameGroup.innerHTML = `<td colspan="6">Full Game Markets</td>`;
            tableBody.insertBefore(fullGameGroup, tableBody.firstChild);
        }
        if (markets.some(m => m.market.includes('1H'))) {
            const halfGameGroup = document.createElement('tr');
            halfGameGroup.className = 'market-group-row';
            halfGameGroup.innerHTML = `<td colspan="6">1st Half Markets</td>`;
            tableBody.appendChild(halfGameGroup);
        }

        card.dataset.maxEv = maxEv !== -Infinity ? maxEv.toString() : '-Infinity';
        if (tableBody.innerHTML !== prevTableBodyHtml && !isNewCard) {
            card.querySelector('.markets-table-container').classList.add('flash-yellow');
            setTimeout(() => card.querySelector('.markets-table-container')?.classList.remove('flash-yellow'), 1500);
        }

        if (isNewCard) {
            card.querySelector('.btn-dismiss').addEventListener('click', () => {
                card.classList.add('dismissed');
                setTimeout(() => card.remove(), 500);
            });
            oddsDisplayArea.appendChild(card);

            const dismissalTimeout = setTimeout(() => {
                card.classList.add('dismissed');
                setTimeout(() => card.remove(), 500);
            }, DISMISSAL_TIMEOUT_MS);

            if (!hasPositiveEv) {
                const noEvTimeout = setTimeout(() => {
                    if (!card.classList.contains('dismissed')) {
                        card.classList.add('dismissed');
                        setTimeout(() => card.remove(), 500);
                    }
                }, NO_EV_TIMEOUT_MS);
                cardTimeouts.set(eventId, noEvTimeout);
            } else {
                console.log(`[Realtime] Scheduling BetBCK refresh for event ${eventId} with +EV`);
                // Placeholder for BetBCK refresh; requires backend endpoint
            }
        } else if (hasPositiveEv && cardTimeouts.has(eventId)) {
            clearTimeout(cardTimeouts.get(eventId));
            cardTimeouts.delete(eventId);
            console.log(`[Realtime] Clearing no-EV timeout for event ${eventId} due to +EV`);
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

            if (currentSignature === lastDataSignature) {
                document.querySelectorAll('.event-container:not(.dismissed)').forEach(card => {
                    const eventId = card.id?.replace('event-', '');
                    if (eventsData[eventId]) {
                        card.querySelector('.event-last-update').textContent = `Odds Updated: ${timeSince(eventsData[eventId].last_pinnacle_data_update_timestamp)}`;
                        card.querySelector('.event-time-since').textContent = `Alert ${timeSince(eventsData[eventId].alert_arrival_timestamp)}`;
                    }
                });
                setStatus('connected', 'Live (No Changes)');
                return; 
            }
            lastDataSignature = currentSignature;
            setStatus('connected', 'Live (Updated)');
            
            mainLoadingMessage.style.display = Object.keys(eventsData).length === 0 ? 'block' : 'none';

            const receivedEventIds = new Set(Object.entries(eventsData).map(([id]) => id));
            
            [...oddsDisplayArea.children].forEach(card => {
                const eventId = card.id?.replace('event-', '');
                if (eventId && !receivedEventIds.has(eventId)) {
                    card.classList.add('dismissed');
                    setTimeout(() => card.remove(), 500);
                }
            });

            for (const [eventId, eventData] of Object.entries(eventsData)) {
                createOrUpdateEventCard(eventId, eventData);
            }
            
            sortCardsByEv();

        } catch (error) {
            console.error("Error refreshing events:", error);
            setStatus('disconnected', 'Connection Error');
        }
    }
    
    fetchAndRefresh();
    setInterval(fetchAndRefresh, REFRESH_INTERVAL_MS);
});