// python_bettor_backend/static/realtime.js
document.addEventListener('DOMContentLoaded', () => {
    const oddsDisplayArea = document.getElementById("oddsDisplayArea");
    const mainLoadingMessage = document.getElementById("mainLoadingMessage");

    if (!oddsDisplayArea) { /* ... */ return; }
    console.log("Realtime.js v7.8 (Pin Spreads/Totals OBJECT Fix, Alert Order, BetBCK) Loaded.");

    const MAX_EVENTS_TO_DISPLAY = 5;
    const REFRESH_INTERVAL_MS = 3000;
    const FLASH_DURATION_MS = 1400;
    const POSITIVE_EV_THRESHOLD = 0.0001;

    let previousDataSnapshot = {};
    let displayedEventIdsOnPage = new Set();

    function formatTimestamp(timestampMs) { /* ... same ... */ 
        if (!timestampMs && timestampMs !== 0) return 'N/A';
        try { return new Date(timestampMs).toLocaleString(); } catch (e) { return 'Invalid Date'; }
    }
    function formatLastUpdate(timestampSeconds) { /* ... same ... */ 
        if (!timestampSeconds && timestampSeconds !== 0) return 'N/A';
        try { return new Date(timestampSeconds * 1000).toLocaleString(); } catch (e) { return 'Invalid Date'; }
    }
    function americanToDecimal(americanOdds) { /* ... same ... */ 
        if (americanOdds === null || americanOdds === undefined || typeof americanOdds === 'string' && (americanOdds.trim() === 'N/A' || americanOdds.trim() === '')) return null;
        const odds = parseFloat(americanOdds);
        if (isNaN(odds)) return null;
        if (odds > 0) return (odds / 100) + 1;
        if (odds < 0) return (100 / Math.abs(odds)) + 1;
        return null;
    }
    function getPinnacleMarketSnapshotKey(periodName, marketType, selection, hdpOrPoints = '') { /* ... same ... */ 
        return `${periodName}-${marketType}-${selection}-${String(hdpOrPoints || '').replace(/\./g, 'p')}`.replace(/\s+/g, '_').toLowerCase();
    }

    function createTableForEvent(eventId, eventEntryFromServer) {
        // ... (Initial variable setup and header HTML generation as in v7.7 is mostly fine) ...
        const pinnacleDataContainer = eventEntryFromServer.pinnacle_data_processed;
        const pinnacleEventDetails = pinnacleDataContainer?.data;
        const alertInfo = eventEntryFromServer.alert_trigger_details || {};
        const betbckFullResponse = eventEntryFromServer.betbck_data;
        const betbckOddsPayload = (betbckFullResponse && betbckFullResponse.status === 'success' && betbckFullResponse.data) ? betbckFullResponse.data : null;

        let tableHtml = '';
        const homeTeam = pinnacleEventDetails?.home || alertInfo.homeTeam || 'Home N/A';
        const awayTeam = pinnacleEventDetails?.away || alertInfo.awayTeam || 'Away N/A';
        const displayPinLastUpdate = eventEntryFromServer.pinnacle_last_update_for_display || eventEntryFromServer.alert_arrival_timestamp;

        tableHtml += `<div class="event-header">${homeTeam} vs ${awayTeam} (ID: ${eventId})</div>`;
        tableHtml += `<div class="event-meta alert-info">` +
                     `<strong>Alert:</strong> ${alertInfo.betDescription || 'N/A'} ` +
                     `(Old: ${alertInfo.oldOdds || 'N/A'} → New: ${alertInfo.newOdds || 'N/A'}, Alert NVP: ${alertInfo.noVigPriceFromAlert || 'N/A'})<br>` +
                     `League: ${pinnacleEventDetails?.league_name || alertInfo.leagueName || 'N/A'} | Starts: ${formatTimestamp(pinnacleEventDetails?.starts)} | Pin Last Update: <span class="pinnacle-last-update">${formatLastUpdate(displayPinLastUpdate)}</span>` +
                     `</div>`;
        tableHtml += `<div class="betbck-status-container">`;
        // ... (BetBCK status display logic from v7.7 is fine) ...
        if (betbckFullResponse) {
            if (betbckFullResponse.status === 'success' && betbckOddsPayload) {
                tableHtml += `<div class="betbck-status success">BetBCK: Odds found for '${betbckOddsPayload.betbck_displayed_local || 'N/A'}' vs '${betbckOddsPayload.betbck_displayed_visitor || 'N/A'}'.</div>`;
            } else if (betbckFullResponse.status !== 'success' && betbckFullResponse.message) {
                tableHtml += `<div class="betbck-status error">BetBCK: ${betbckFullResponse.message} (For POD: ${alertInfo.homeTeam || 'N/A'} vs ${alertInfo.awayTeam || 'N/A'})</div>`;
            } else if (betbckFullResponse.status === 'success' && !betbckOddsPayload) {
                tableHtml += `<div class="betbck-status warning">BetBCK: Scraper success but no odds payload.</div>`;
            }
        } else {
            tableHtml += `<div class="betbck-status info">BetBCK: Odds check not run or pending.</div>`;
        }
        tableHtml += `</div>`;


        if (!pinnacleEventDetails || !pinnacleEventDetails.periods) {
            tableHtml += `<p class="error">${pinnacleDataContainer?.error || 'Pinnacle live odds data or periods missing.'}</p>`;
            return tableHtml;
        }

        const previousPinnacleMarkets = previousDataSnapshot[eventId]?.markets || {};
        const newPinnacleMarketsSnapshot = {};

        tableHtml += `<table><thead><tr>
            <th>Market</th><th>Selection</th><th>Line</th>
            <th>Pinnacle Odds (Am)</th><th class="nvp">Pinnacle NVP (Am)</th>
            <th>BetBCK Odds (Am)</th><th class="ev">EV %</th>
        </tr></thead><tbody>`;

        const appendMarketRows = (currentPeriodData, periodName) => {
            if (!currentPeriodData || typeof currentPeriodData !== 'object') return;

            const renderRow = (marketType, selectionName, lineDisplay, pinOddsAm, pinNvpAm, betbckOddsAm) => {
                // ... (renderRow logic from v7.7 is fine for EV calc and display) ...
                let pinDisplay = pinOddsAm !== undefined && pinOddsAm !== null ? pinOddsAm : 'N/A';
                let pinNvpDisplay = pinNvpAm !== undefined && pinNvpAm !== null ? pinNvpAm : 'N/A';
                let bckDisplay = betbckOddsAm !== undefined && betbckOddsAm !== null ? betbckOddsAm : 'N/A';
                let evDisplay = 'N/A'; let rowClass = '';

                const pMarketKey = getPinnacleMarketSnapshotKey(periodName, marketType, selectionName, lineDisplay);
                let pCellClass = (previousPinnacleMarkets.hasOwnProperty(pMarketKey) && previousPinnacleMarkets[pMarketKey] !== pinDisplay) ? 'odds-changed' : '';
                newPinnacleMarketsSnapshot[pMarketKey] = pinDisplay;

                if (pinNvpDisplay !== 'N/A' && bckDisplay !== 'N/A') {
                    const pinNvpDec = americanToDecimal(pinNvpDisplay);
                    const bckDec = americanToDecimal(bckDisplay);
                    if (pinNvpDec && bckDec && pinNvpDec > 1.0001) {
                        const evValue = (bckDec / pinNvpDec) - 1;
                        evDisplay = (evValue * 100).toFixed(2) + '%';
                        rowClass = evValue > POSITIVE_EV_THRESHOLD ? 'positive-ev' : (evValue < -POSITIVE_EV_THRESHOLD ? 'negative-ev' : '');
                    }
                }
                tableHtml += `<tr class="${rowClass}"><td>${marketType}</td><td>${selectionName}</td><td>${lineDisplay || ''}</td><td class="${pCellClass}">${pinDisplay}</td><td class="nvp ${pCellClass}">${pinNvpDisplay}</td><td class="betbck-odds">${bckDisplay}</td><td class="ev">${evDisplay}</td></tr>`;
            };

            if (currentPeriodData.money_line && typeof currentPeriodData.money_line === 'object') {
                // ... (Moneyline rendering from v7.7 is fine) ...
                const ml = currentPeriodData.money_line;
                tableHtml += `<tr class="market-group"><td colspan="7">Moneyline (${periodName})</td></tr>`;
                renderRow("Moneyline", homeTeam, '', ml.american_home, ml.nvp_american_home, betbckOddsPayload?.home_moneyline_american);
                renderRow("Moneyline", awayTeam, '', ml.american_away, ml.nvp_american_away, betbckOddsPayload?.away_moneyline_american);
                if (ml.american_draw !== undefined && ml.american_draw !== null && ml.american_draw !== 'N/A') {
                    renderRow("Moneyline", "Draw", '', ml.american_draw, ml.nvp_american_draw, betbckOddsPayload?.draw_moneyline_american);
                }
            }

            // Spreads: CORRECTED to use Object.values() for Pinnacle data
            if (currentPeriodData.spreads && typeof currentPeriodData.spreads === 'object' && !Array.isArray(currentPeriodData.spreads)) {
                const spreadsArray = Object.values(currentPeriodData.spreads); // Use Object.values
                if (spreadsArray.length > 0) tableHtml += `<tr class="market-group"><td colspan="7">Spreads (${periodName})</td></tr>`;
                spreadsArray.forEach(s => { // 's' is each spread object
                    if (typeof s !== 'object' || s.hdp === undefined) {
                         console.warn(`[JS ${eventId}] Invalid spread object or missing hdp in Pinnacle data:`, s);
                        return;
                    }
                    const homeLineStr = s.hdp > 0 ? `+${s.hdp}` : `${s.hdp}`;
                    const awayLine = -s.hdp;
                    const awayLineStr = awayLine === 0 ? "0" : (awayLine > 0 ? `+${awayLine}` : `${awayLine}`);
                    let bckHomeSpread = null, bckAwaySpread = null;
                    if (betbckOddsPayload) {
                        bckHomeSpread = betbckOddsPayload.home_spreads?.find(bs => bs.line === homeLineStr)?.odds;
                        bckAwaySpread = betbckOddsPayload.away_spreads?.find(bs => bs.line === awayLineStr)?.odds;
                    }
                    renderRow("Spread", homeTeam, homeLineStr, s.american_home, s.nvp_american_home, bckHomeSpread);
                    renderRow("Spread", awayTeam, awayLineStr, s.american_away, s.nvp_american_away, bckAwaySpread);
                });
            }  else if (Array.isArray(currentPeriodData.spreads)) { // Fallback if it's already an array (unlikely based on your JSON)
                 console.warn(`[JS ${eventId}] Spreads data for period ${periodName} was an Array, processing as such.`);
                 if (currentPeriodData.spreads.length > 0) tableHtml += `<tr class="market-group"><td colspan="7">Spreads (${periodName})</td></tr>`;
                 currentPeriodData.spreads.forEach(s => { /* ... same as above ... */ });
            } else if (currentPeriodData.spreads) {
                console.warn(`[JS ${eventId}] Spreads data for period ${periodName} is neither an object nor an array:`, currentPeriodData.spreads);
            }


            // Totals: CORRECTED to use Object.values() for Pinnacle data
            if (currentPeriodData.totals && typeof currentPeriodData.totals === 'object' && !Array.isArray(currentPeriodData.totals)) {
                const totalsArray = Object.values(currentPeriodData.totals); // Use Object.values
                if (totalsArray.length > 0) tableHtml += `<tr class="market-group"><td colspan="7">Totals (${periodName})</td></tr>`;
                totalsArray.forEach(t => { // 't' is each total object
                    if (typeof t !== 'object' || t.points === undefined) {
                        console.warn(`[JS ${eventId}] Invalid total object or missing points in Pinnacle data:`, t);
                        return;
                    }
                    const pointsStr = `${t.points}`;
                    let bckOverOdds = null, bckUnderOdds = null;
                    if (betbckOddsPayload && String(betbckOddsPayload.game_total_line) === pointsStr) {
                        bckOverOdds = betbckOddsPayload.game_total_over_odds;
                        bckUnderOdds = betbckOddsPayload.game_total_under_odds;
                    }
                    renderRow("Total", "Over", pointsStr, t.american_over, t.nvp_american_over, bckOverOdds);
                    renderRow("Total", "Under", pointsStr, t.american_under, t.nvp_american_under, bckUnderOdds);
                });
            } else if (Array.isArray(currentPeriodData.totals)) {
                 console.warn(`[JS ${eventId}] Totals data for period ${periodName} was an Array, processing as such.`);
                 if (currentPeriodData.totals.length > 0) tableHtml += `<tr class="market-group"><td colspan="7">Totals (${periodName})</td></tr>`;
                 currentPeriodData.totals.forEach(t => { /* ... same as above ... */});
            } else if (currentPeriodData.totals) {
                console.warn(`[JS ${eventId}] Totals data for period ${periodName} is neither an object nor an array:`, currentPeriodData.totals);
            }
        };

        // ... (Calling appendMarketRows for period0, period1, and the rest of createTableForEvent from v7.7 is fine) ...
        const period0 = pinnacleEventDetails.periods?.num_0;
        const period1 = pinnacleEventDetails.periods?.num_1;
        if (period0) appendMarketRows(period0, "Match");
        if (period1) appendMarketRows(period1, "1st Half");
        if (!period0 && !period1 && Object.keys(pinnacleEventDetails.periods || {}).length === 0) {
            tableHtml += '<tr><td colspan="7">No detailed period odds in Pinnacle data.</td></tr>';
        }
        tableHtml += '</tbody></table>';

        previousDataSnapshot[eventId] = {
            markets: newPinnacleMarketsSnapshot,
            pinnacleLastUpdateTs: pinnacleEventDetails.last,
            alertArrivalTs: eventEntryFromServer.alert_arrival_timestamp,
            betbckStatus: betbckFullResponse?.status 
        };
        return tableHtml;
    }

    async function fetchAndRefreshAllActiveEvents() {
        // ... (This function from v7.7, which handles sorting by alert_arrival_timestamp and DOM updates, is largely correct
        //      assuming server.py sends 'alert_arrival_timestamp' correctly.) ...
        try {
            const response = await fetch(`http://localhost:5001/get_active_events_data`);
            if (!response.ok) { 
                console.error(`HTTP error ${response.status} fetching active events.`);
                if (mainLoadingMessage) mainLoadingMessage.textContent = `Error fetching (HTTP ${response.status})`;
                return;
            }
            const allEventsDataFromServer = await response.json();
            
            const sortedEventEntries = Object.entries(allEventsDataFromServer)
                .sort(([, a_entry], [, b_entry]) => (b_entry.alert_arrival_timestamp || 0) - (a_entry.alert_arrival_timestamp || 0))
                .slice(0, MAX_EVENTS_TO_DISPLAY);

            if (mainLoadingMessage) {
                const noEventsCurrently = sortedEventEntries.length === 0 && displayedEventIdsOnPage.size === 0;
                mainLoadingMessage.style.display = noEventsCurrently ? 'block' : 'none';
                if (noEventsCurrently) mainLoadingMessage.textContent = "No active alerts. Waiting for POD alerts...";
            }

            const receivedEventIdsThisFetch = new Set(sortedEventEntries.map(([eventId, _]) => eventId));
            
            const currentDivIdsOnPage = Array.from(oddsDisplayArea.children).map(child => child.id.replace('event-container-', ''));
            currentDivIdsOnPage.forEach(displayedId => {
                if (!receivedEventIdsThisFetch.has(displayedId)) {
                    const eventDiv = document.getElementById(`event-container-${displayedId}`);
                    if (eventDiv) eventDiv.remove();
                    delete previousDataSnapshot[displayedId];
                    displayedEventIdsOnPage.delete(displayedId);
                }
            });
            
            const divsInCorrectOrder = [];
            for (const [eventId, eventEntry] of sortedEventEntries) {
                let eventDiv = document.getElementById(`event-container-${eventId}`);
                let isNewContentGenerationNeeded = !eventDiv; 

                if (!eventDiv) {
                    eventDiv = document.createElement('div');
                    eventDiv.className = 'event-container';
                    eventDiv.id = `event-container-${eventId}`;
                }
                
                const prevSnapshot = previousDataSnapshot[eventId];
                const currentPinDataLastUpdate = eventEntry.pinnacle_data_processed?.data?.last; // Pinnacle data last field
                const currentPinAlertLastUpdate = eventEntry.pinnacle_last_update_for_display; // Server's record of last update
                const currentBetBCKStatus = eventEntry.betbck_data?.status;


                if (!prevSnapshot ||
                    (prevSnapshot.pinnacleLastUpdateTs !== currentPinDataLastUpdate) || 
                    prevSnapshot.betbckStatus !== currentBetBCKStatus ||
                    prevSnapshot.alertArrivalTs !== eventEntry.alert_arrival_timestamp ) { // If any key data changed
                    isNewContentGenerationNeeded = true; 
                }
                
                if (isNewContentGenerationNeeded) {
                    const newHtml = createTableForEvent(eventId, eventEntry);
                    eventDiv.innerHTML = newHtml;
                    eventDiv.querySelectorAll('.odds-changed').forEach(cell => {
                        cell.classList.add('flash-yellow');
                        setTimeout(() => {
                            cell.classList.remove('flash-yellow');
                            cell.classList.remove('odds-changed'); 
                        }, FLASH_DURATION_MS);
                    });
                }
                divsInCorrectOrder.push(eventDiv); 
                 if (!displayedEventIdsOnPage.has(eventId) && !document.getElementById(`event-container-${eventId}`)) { 
                    displayedEventIdsOnPage.add(eventId); // Add only if truly new to the page conceptually
                }
            }

            let currentDomOrder = Array.from(oddsDisplayArea.children);
            let domNeedsReorder = divsInCorrectOrder.length !== currentDomOrder.length;
            if (!domNeedsReorder) {
                for(let i=0; i < divsInCorrectOrder.length; i++) {
                    if (!currentDomOrder[i] || currentDomOrder[i].id !== divsInCorrectOrder[i].id) {
                        domNeedsReorder = true; break;
                    }
                }
            }

            if (domNeedsReorder) {
                while (oddsDisplayArea.firstChild) oddsDisplayArea.removeChild(oddsDisplayArea.firstChild);
                divsInCorrectOrder.forEach(div => oddsDisplayArea.appendChild(div));
            }
             // Ensure displayedEventIdsOnPage accurately reflects what's in divsInCorrectOrder
            const newDisplayedIds = new Set(divsInCorrectOrder.map(div => div.id.replace('event-container-', '')));
            displayedEventIdsOnPage.forEach(id => {
                if (!newDisplayedIds.has(id)) displayedEventIdsOnPage.delete(id);
            });
            newDisplayedIds.forEach(id => displayedEventIdsOnPage.add(id));


        } catch (error) { 
            console.error("[Realtime.js] Error refreshing events:", error);
            if (mainLoadingMessage) {
                mainLoadingMessage.textContent = `Error updating view: ${error.message || String(error)}`;
                mainLoadingMessage.style.display = 'block';
            }
        }
    }
    
    if (mainLoadingMessage) mainLoadingMessage.textContent = "Fetching initial event data...";
    fetchAndRefreshAllActiveEvents();
    setInterval(fetchAndRefreshAllActiveEvents, REFRESH_INTERVAL_MS);
});