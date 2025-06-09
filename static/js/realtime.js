// static/js/realtime.js
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
    console.log("Realtime.js v10.0 (Modern UI) Loaded.");

    const REFRESH_INTERVAL_MS = 3000;
    const POSITIVE_EV_THRESHOLD = 0.0001; // 0.01%
    let lastDataTimestamp = 0;

    function setStatus(state, message) {
        statusIndicator.className = `status-${state}`;
        statusText.textContent = message;
    }

    function timeSince(timestamp) {
        if (!timestamp) return 'N/A';
        const seconds = Math.floor((new Date() - new Date(timestamp * 1000)) / 1000);
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

    function createOrUpdateEventCard(eventId, eventData) {
        let card = document.getElementById(`event-${eventId}`);
        const isNewCard = !card;

        if (isNewCard) {
            card = cardTemplate.content.cloneNode(true).firstElementChild;
            card.id = `event-${eventId}`;
        }

        const pinnacleData = eventData.pinnacle_data_processed?.data || {};
        const alertDetails = eventData.alert_trigger_details || {};
        const betbckData = eventData.betbck_data || {};
        const betbckPayload = betbckData.status === 'success' ? betbckData.data : null;

        const homeTeam = pinnacleData.home || alertDetails.homeTeam || 'N/A';
        const awayTeam = pinnacleData.away || alertDetails.awayTeam || 'N/A';
        
        // --- Populate Header ---
        card.querySelector('.event-title').textContent = `${homeTeam} vs ${awayTeam}`;
        const leagueName = pinnacleData.league_name || alertDetails.leagueName || 'Unknown League';
        const startTime = pinnacleData.starts ? new Date(pinnacleData.starts).toLocaleString() : 'N/A';
        card.querySelector('.event-meta-info').textContent = `${leagueName} | Starts: ${startTime}`;
        card.querySelector('.event-time-since').textContent = `Alert ${timeSince(eventData.alert_arrival_timestamp)}`;
        
        // --- Populate Alert Banner ---
        const oldOdds = alertDetails.oldOdds || 'N/A';
        const newOdds = alertDetails.newOdds || 'N/A';
        card.querySelector('.alert-description').textContent = alertDetails.betDescription || 'N/A';
        card.querySelector('.alert-meta').textContent = `(Alert: ${oldOdds} → ${newOdds}, NVP: ${alertDetails.noVigPriceFromAlert || 'N/A'})`;

        // --- Populate BetBCK Status ---
        const bckStatusContainer = card.querySelector('.betbck-status-container');
        let bckStatusHtml = '';
        if (betbckData.status === 'success' && betbckPayload) {
            bckStatusHtml = `<p class="betbck-status success">BetBCK: Odds found for '${betbckPayload.betbck_displayed_local}' vs '${betbckPayload.betbck_displayed_visitor}'</p>`;
        } else if (betbckData.status && betbckData.message) {
            bckStatusHtml = `<p class="betbck-status error">BetBCK: ${betbckData.message}</p>`;
        } else {
            bckStatusHtml = `<p class="betbck-status info">BetBCK: Odds check pending...</p>`;
        }
        bckStatusContainer.innerHTML = bckStatusHtml;
        
        // --- Populate Markets Table ---
        const tableBody = card.querySelector('tbody');
        const prevTableBodyHtml = tableBody.innerHTML;
        tableBody.innerHTML = ''; // Clear old rows
        let maxEv = -Infinity;

        const renderRow = (marketType, selectionName, lineDisplay, pinNvpAm, bckOddsAm) => {
            const row = document.createElement('tr');
            const pinNvpDisplay = pinNvpAm || 'N/A';
            const bckDisplay = bckOddsAm || 'N/A';
            let evDisplay = 'N/A';
            let rowClass = '';

            if (pinNvpDisplay !== 'N/A' && bckDisplay !== 'N/A') {
                const pinNvpDec = parseFloat(pinNvpDisplay) > 0 ? (parseFloat(pinNvpDisplay) / 100) + 1 : (100 / Math.abs(parseFloat(pinNvpDisplay))) + 1;
                const bckDec = parseFloat(bckOddsAm) > 0 ? (parseFloat(bckOddsAm) / 100) + 1 : (100 / Math.abs(parseFloat(bckOddsAm))) + 1;
                if (pinNvpDec && bckDec && pinNvpDec > 1.0001) {
                    const evValue = (bckDec / pinNvpDec) - 1;
                    evDisplay = (evValue * 100).toFixed(2) + '%';
                    maxEv = Math.max(maxEv, evValue);
                    rowClass = evValue > POSITIVE_EV_THRESHOLD ? 'positive-ev' : 'negative-ev';
                }
            }

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
        
        const appendMarketRows = (periodData, periodName) => {
            if (!periodData) return;
            const marketGroup = document.createElement('tr');
            marketGroup.className = 'market-group-row';
            marketGroup.innerHTML = `<td colspan="6">${periodName} Markets</td>`;
            tableBody.appendChild(marketGroup);
            
            // Moneyline
            if (periodData.money_line) {
                const ml = periodData.money_line;
                tableBody.appendChild(renderRow('Moneyline', homeTeam, '', ml.nvp_american_home, betbckPayload?.home_moneyline_american));
                tableBody.appendChild(renderRow('Moneyline', awayTeam, '', ml.nvp_american_away, betbckPayload?.away_moneyline_american));
                if (ml.nvp_american_draw) {
                    tableBody.appendChild(renderRow('Moneyline', 'Draw', '', ml.nvp_american_draw, betbckPayload?.draw_moneyline_american));
                }
            }
            // Spreads
            if (periodData.spreads) {
                Object.values(periodData.spreads).forEach(s => {
                    const homeLine = s.hdp > 0 ? `+${s.hdp}` : `${s.hdp}`;
                    const awayLine = -s.hdp > 0 ? `+${-s.hdp}`: `${-s.hdp}`;
                    const bckHomeSpread = betbckPayload?.home_spreads?.find(bs => bs.line === homeLine)?.odds;
                    const bckAwaySpread = betbckPayload?.away_spreads?.find(bs => bs.line === awayLine)?.odds;
                    tableBody.appendChild(renderRow('Spread', homeTeam, homeLine, s.nvp_american_home, bckHomeSpread));
                    tableBody.appendChild(renderRow('Spread', awayTeam, awayLine, s.nvp_american_away, bckAwaySpread));
                });
            }
            // Totals
            if (periodData.totals) {
                Object.values(periodData.totals).forEach(t => {
                    const line = t.points;
                    let bckOver, bckUnder;
                    if (betbckPayload && String(betbckPayload.game_total_line) === String(line)) {
                        bckOver = betbckPayload.game_total_over_odds;
                        bckUnder = betbckPayload.game_total_under_odds;
                    }
                    tableBody.appendChild(renderRow('Total', 'Over', line, t.nvp_american_over, bckOver));
                    tableBody.appendChild(renderRow('Total', 'Under', line, t.nvp_american_under, bckUnder));
                });
            }
        };

        appendMarketRows(pinnacleData.periods?.num_0, "Full Game");
        appendMarketRows(pinnacleData.periods?.num_1, "1st Half");
        
        card.dataset.maxEv = maxEv; // Store max EV for sorting
        if (tableBody.innerHTML !== prevTableBodyHtml && !isNewCard) {
            card.querySelector('.markets-table-container').classList.add('flash-yellow');
            setTimeout(() => card.querySelector('.markets-table-container').classList.remove('flash-yellow'), 1500);
        }

        if (isNewCard) {
            card.querySelector('.btn-dismiss').addEventListener('click', () => {
                card.classList.add('dismissed');
                // After animation, remove from DOM to keep things tidy
                setTimeout(() => card.remove(), 500);
            });
            oddsDisplayArea.appendChild(card);
        }
        
        return card;
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
            const response = await fetch('/get_active_events_data');
            if (!response.ok) throw new Error(`HTTP error ${response.status}`);
            
            const eventsData = await response.json();
            const now = Date.now();
            
            if (Object.keys(eventsData).length === 0 && oddsDisplayArea.children.length <= 1) { // <=1 to account for loading message
                mainLoadingMessage.style.display = 'block';
            } else {
                mainLoadingMessage.style.display = 'none';
            }

            if (JSON.stringify(eventsData).length === lastDataTimestamp) {
                setStatus('connected', 'Live (No Changes)');
                return; // No changes, skip DOM updates
            }
            lastDataTimestamp = JSON.stringify(eventsData).length;
            setStatus('connected', 'Live (Updated)');

            const receivedEventIds = new Set(Object.keys(eventsData));
            
            // Remove cards for events that are no longer active
            [...oddsDisplayArea.children].forEach(card => {
                const eventId = card.id.replace('event-', '');
                if (eventId && !receivedEventIds.has(eventId)) {
                    card.classList.add('dismissed');
                    setTimeout(() => card.remove(), 500);
                }
            });

            // Add or update cards
            for (const [eventId, eventData] of Object.entries(eventsData)) {
                createOrUpdateEventCard(eventId, eventData);
            }
            
            sortCardsByEv();

        } catch (error) {
            console.error("Error refreshing events:", error);
            setStatus('disconnected', 'Connection Error');
        }
    }
    
    // Initial fetch and set interval
    fetchAndRefresh();
    setInterval(fetchAndRefresh, REFRESH_INTERVAL_MS);
});