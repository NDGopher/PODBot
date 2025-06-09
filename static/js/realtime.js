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
    console.log("Realtime.js v11.0 (Popups & Timestamps) Loaded.");

    const REFRESH_INTERVAL_MS = 3000;
    const POSITIVE_EV_THRESHOLD = 0.0001; // 0.01%
    let lastDataSignature = "";

    // --- NEW: Popup Management ---
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

    // --- NEW: Popup Function ---
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

        popup.document.title = `+EV Alert: ${selectionName}`;
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
            <p><strong>BetBCK Odds:</strong> ${bckDisplay}</p>
            <p><strong>Pinnacle NVP:</strong> ${pinNvpDisplay}</p>
            <p class="ev-value">EV: ${evDisplay}</p>
        `;
    }

    function createOrUpdateEventCard(eventId, eventData) {
        let card = document.getElementById(`event-${eventId}`);
        const isNewCard = !card;

        if (isNewCard) {
            card = cardTemplate.content.cloneNode(true).firstElementChild;
            card.id = `event-${eventId}`;
        }

        const pinnacleData = eventData.pinnacle_data_processed?.data || {};
        const alertDetails = eventData.original_alert_details || {}; // Corrected key name
        const betbckPayload = eventData.betbck_data?.data || null;

        const homeTeam = pinnacleData.home || alertDetails.homeTeam || 'N/A';
        const awayTeam = pinnacleData.away || alertDetails.awayTeam || 'N/A';
        
        card.querySelector('.event-title').textContent = `${homeTeam} vs ${awayTeam}`;
        const leagueName = pinnacleData.league_name || alertDetails.leagueName || 'Unknown League';
        const startTime = pinnacleData.starts ? new Date(pinnacleData.starts).toLocaleString() : 'N/A';
        card.querySelector('.event-meta-info').textContent = `${leagueName} | Starts: ${startTime}`;
        
        // --- FIX: Update "Last Updated" timestamp ---
        const lastUpdateTimestamp = eventData.last_pinnacle_data_update_timestamp;
        card.querySelector('.event-last-update').textContent = `Odds Updated: ${timeSince(lastUpdateTimestamp)}`;
        card.querySelector('.event-time-since').textContent = `Alert ${timeSince(eventData.alert_arrival_timestamp)}`;
        
        // --- FIX: Correctly populate alert banner ---
        const oldOdds = alertDetails.oldOdds || 'N/A';
        const newOdds = alertDetails.newOdds || 'N/A';
        const betDesc = alertDetails.betDescription || 'N/A';
        const noVig = alertDetails.noVigPriceFromAlert || 'N/A';
        card.querySelector('.alert-description').textContent = betDesc;
        card.querySelector('.alert-meta').textContent = `(Alert: ${oldOdds} → ${newOdds}, NVP: ${noVig})`;

        const bckStatusContainer = card.querySelector('.betbck-status-container');
        if (eventData.betbck_data?.status === 'success' && betbckPayload) {
            bckStatusContainer.innerHTML = `<p class="betbck-status success">BetBCK: Odds found for '${betbckPayload.betbck_displayed_local}' vs '${betbckPayload.betbck_displayed_visitor}'</p>`;
        } else if (eventData.betbck_data?.message) {
            bckStatusContainer.innerHTML = `<p class="betbck-status error">BetBCK: ${eventData.betbck_data.message}</p>`;
        } else {
            bckStatusContainer.innerHTML = `<p class="betbck-status info">BetBCK: Odds check pending...</p>`;
        }
        
        const tableBody = card.querySelector('tbody');
        const prevTableBodyHtml = tableBody.innerHTML;
        tableBody.innerHTML = ''; 
        let maxEv = -Infinity;

        const renderRow = (marketType, selectionName, lineDisplay, pinNvpAm, bckOddsAm, periodName) => {
            const pinNvpDisplay = pinNvpAm || 'N/A';
            const bckDisplay = bckOddsAm || 'N/A';
            let evDisplay = 'N/A';
            let rowClass = '';

            if (pinNvpDisplay !== 'N/A' && bckDisplay !== 'N/A') {
                const pinNvpDec = americanToDecimal(pinNvpDisplay);
                const bckDec = americanToDecimal(bckOddsAm);
                if (pinNvpDec && bckDec && pinNvpDec > 1.0001) {
                    const evValue = (bckDec / pinNvpDec) - 1;
                    evDisplay = (evValue * 100).toFixed(2) + '%';
                    maxEv = Math.max(maxEv, evValue);
                    rowClass = evValue > POSITIVE_EV_THRESHOLD ? 'positive-ev' : 'negative-ev';

                    // --- ADDED: Trigger popup on new positive EV bets ---
                    if (isNewCard && evValue > POSITIVE_EV_THRESHOLD) {
                        showPositiveEvPopup(
                            { eventId, homeTeam, awayTeam, periodName },
                            { selectionName, lineDisplay, marketType, bckDisplay, pinNvpDisplay, evDisplay }
                        );
                    }
                }
            }

            if (evDisplay === 'N/A') {
                return null;
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
        
        const appendMarketRows = (periodData, periodName) => {
            if (!periodData || Object.keys(periodData).length === 0) return;
            const marketRows = []; 

            if (periodData.money_line) {
                const ml = periodData.money_line;
                marketRows.push(renderRow('Moneyline', homeTeam, '', ml.nvp_american_home, betbckPayload?.home_moneyline_american, periodName));
                marketRows.push(renderRow('Moneyline', awayTeam, '', ml.nvp_american_away, betbckPayload?.away_moneyline_american, periodName));
                if (ml.nvp_american_draw) {
                    marketRows.push(renderRow('Moneyline', 'Draw', '', ml.nvp_american_draw, betbckPayload?.draw_moneyline_american, periodName));
                }
            }
            if (periodData.spreads) {
                Object.values(periodData.spreads).forEach(s => {
                    const homeLine = s.hdp > 0 ? `+${s.hdp}` : `${s.hdp}`;
                    const awayLine = -s.hdp === 0 ? '0' : (-s.hdp > 0 ? `+${-s.hdp}`: `${-s.hdp}`);
                    const bckHomeSpread = betbckPayload?.home_spreads?.find(bs => bs.line === homeLine)?.odds;
                    const bckAwaySpread = betbckPayload?.away_spreads?.find(bs => bs.line === awayLine)?.odds;
                    marketRows.push(renderRow('Spread', homeTeam, homeLine, s.nvp_american_home, bckHomeSpread, periodName));
                    marketRows.push(renderRow('Spread', awayTeam, awayLine, s.nvp_american_away, bckAwaySpread, periodName));
                });
            }
            if (periodData.totals) {
                Object.values(periodData.totals).forEach(t => {
                    const line = String(t.points);
                    let bckOver, bckUnder;
                    if (betbckPayload && String(betbckPayload.game_total_line) === line) {
                        bckOver = betbckPayload.game_total_over_odds;
                        bckUnder = betbckPayload.game_total_under_odds;
                    }
                    marketRows.push(renderRow('Total', 'Over', line, t.nvp_american_over, bckOver, periodName));
                    marketRows.push(renderRow('Total', 'Under', line, t.nvp_american_under, bckUnder, periodName));
                });
            }

            if (marketRows.some(row => row !== null)) {
                const marketGroup = document.createElement('tr');
                marketGroup.className = 'market-group-row';
                marketGroup.innerHTML = `<td colspan="6">${periodName} Markets</td>`;
                tableBody.appendChild(marketGroup);
                marketRows.forEach(row => {
                    if (row) tableBody.appendChild(row);
                });
            }
        };

        appendMarketRows(pinnacleData.periods?.num_0, "Full Game");
        appendMarketRows(pinnacleData.periods?.num_1, "1st Half");
        
        card.dataset.maxEv = maxEv;
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
            const response = await fetch('/get_active_events_data');
            if (!response.ok) throw new Error(`HTTP error ${response.status}`);
            
            const eventsData = await response.json();
            const currentSignature = JSON.stringify(eventsData);

            if (currentSignature === lastDataSignature) {
                // Still update timestamps even if data is the same
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

            const receivedEventIds = new Set(Object.keys(eventsData));
            
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