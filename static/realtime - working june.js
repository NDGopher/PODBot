// python_bettor_backend/static/realtime.js
document.addEventListener('DOMContentLoaded', () => {
    const oddsDisplayArea = document.getElementById("oddsDisplayArea");
    const mainLoadingMessage = document.getElementById("mainLoadingMessage");

    if (!oddsDisplayArea) { console.error("Realtime.js: #oddsDisplayArea missing!"); return; }
    console.log("Realtime.js v7.9 (Conditional BetBCK Row Display, Alert Order) Loaded.");

    const MAX_EVENTS_TO_DISPLAY = 5;
    const REFRESH_INTERVAL_MS = 3000;
    const FLASH_DURATION_MS = 1400;
    const POSITIVE_EV_THRESHOLD = 0.0001; 

    let previousDataSnapshot = {};
    let displayedEventIdsOnPage = new Set();

    function formatTimestamp(ts) { /* ... same ... */ if (!ts && ts !== 0) return 'N/A'; try { return new Date(ts).toLocaleString(); } catch (e) { return 'Invalid Date'; } }
    function formatLastUpdate(ts) { /* ... same ... */ if (!ts && ts !== 0) return 'N/A'; try { return new Date(ts * 1000).toLocaleString(); } catch (e) { return 'Invalid Date'; } }
    function americanToDecimal(oddsAm) { /* ... same ... */ if (oddsAm===null || oddsAm===undefined || typeof oddsAm === 'string' && (oddsAm.trim()==='N/A'||oddsAm.trim()==='')) return null; const o=parseFloat(oddsAm); if(isNaN(o)) return null; if (o>0) return (o/100)+1; if (o<0) return (100/Math.abs(o))+1; return null; }
    function getPinnacleMarketSnapshotKey(pName, mType, sel, hdpOrPts = '') { /* ... same ... */ return `${pName}-${mType}-${sel}-${String(hdpOrPts||'').replace(/\./g,'p')}`.replace(/\s+/g,'_').toLowerCase(); }

    function createTableForEvent(eventId, eventEntryFromServer) {
        const pinnacleDataContainer = eventEntryFromServer.pinnacle_data_processed;
        const pinnacleEventDetails = pinnacleDataContainer?.data;
        const alertInfo = eventEntryFromServer.alert_trigger_details || {};
        const betbckFullResponse = eventEntryFromServer.betbck_data; // This is the object from main_logic
        const betbckOddsPayload = (betbckFullResponse && betbckFullResponse.status === 'success' && betbckFullResponse.data) ? betbckFullResponse.data : null;

        const homeTeam = pinnacleEventDetails?.home || alertInfo.homeTeam || 'Home N/A';
        const awayTeam = pinnacleEventDetails?.away || alertInfo.awayTeam || 'Away N/A';
        const displayPinLastUpdate = eventEntryFromServer.pinnacle_last_update_for_display || eventEntryFromServer.alert_arrival_timestamp;

        let tableHtml = `<div class="event-header">${homeTeam} vs ${awayTeam} (ID: ${eventId})</div>`;
        tableHtml += `<div class="event-meta alert-info">` +
                     `<strong>Alert:</strong> ${alertInfo.betDescription || 'N/A'} ` +
                     `(Old: ${alertInfo.oldOdds || 'N/A'} → New: ${alertInfo.newOdds || 'N/A'}, Alert NVP: ${alertInfo.noVigPriceFromAlert || 'N/A'})<br>` +
                     `League: ${pinnacleEventDetails?.league_name || alertInfo.leagueName || 'N/A'} | Starts: ${formatTimestamp(pinnacleEventDetails?.starts)} | Pin Last Update: <span class="pinnacle-last-update">${formatLastUpdate(displayPinLastUpdate)}</span>` +
                     `</div>`;
        
        tableHtml += `<div class="betbck-status-container">`;
        if (betbckFullResponse) {
            if (betbckFullResponse.status === 'success' && betbckOddsPayload) {
                tableHtml += `<div class="betbck-status success">BetBCK: Odds data found for '${betbckOddsPayload.betbck_displayed_local || 'N/A'}' vs '${betbckOddsPayload.betbck_displayed_visitor || 'N/A'}'.</div>`;
            } else if (betbckFullResponse.status !== 'success' && betbckFullResponse.message) {
                tableHtml += `<div class="betbck-status error">BetBCK: ${betbckFullResponse.message}</div>`;
            } else { // Catch other states e.g. success but no data
                tableHtml += `<div class="betbck-status warning">BetBCK: Scraper ran, but no specific odds data returned.</div>`;
            }
        } else {
            tableHtml += `<div class="betbck-status info">BetBCK: Odds check pending or not attempted yet.</div>`;
        }
        tableHtml += `</div>`;

        // If BetBCK scrape failed (and didn't return data), do NOT show the odds table at all.
        if (betbckFullResponse && betbckFullResponse.status !== 'success' && !betbckOddsPayload) {
            // No odds table will be generated, only the header and BetBCK status.
            // We still need to update the snapshot for this event to prevent constant re-rendering of the error message.
             previousDataSnapshot[eventId] = {
                markets: {}, // No pinnacle markets to flash if we are hiding the table
                pinnacleLastUpdateTs: pinnacleEventDetails?.last,
                alertArrivalTs: eventEntryFromServer.alert_arrival_timestamp,
                betbckStatus: betbckFullResponse?.status 
            };
            return tableHtml; 
        }
        
        // If Pinnacle data is missing, show error and don't proceed with table body
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
                // If betbckOddsPayload exists (meaning scrape was successful and returned data)
                // but betbckOddsAm for this specific line is null/N/A, we still show the Pinnacle row,
                // but BetBCK cells will be N/A.
                if (!betbckOddsPayload && betbckOddsAm !== undefined) { // If no betbck payload at all, all betbck odds are N/A
                    betbckOddsAm = null;
                }

                // Logic to HIDE rows where BetBCK is N/A IF BetBCK data WAS successfully fetched
                // This means we only show rows where a BetBCK odd EXISTS to compare
                if (betbckOddsPayload && (betbckOddsAm === null || betbckOddsAm === undefined || String(betbckOddsAm).trim() === 'N/A')) {
                    // console.log(`Skipping row for ${marketType} - ${selectionName} ${lineDisplay || ''} due to N/A BetBCK odd when BetBCK data is present.`);
                    return; // Skip rendering this entire row
                }


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

            // Moneyline
            if (currentPeriodData.money_line && typeof currentPeriodData.money_line === 'object') {
                const ml = currentPeriodData.money_line;
                // Determine if any BetBCK ML odd exists for this period before printing header
                let hasBetbckMl = false;
                if (betbckOddsPayload) {
                    if (betbckOddsPayload.home_moneyline_american || betbckOddsPayload.away_moneyline_american || ml.american_draw && betbckOddsPayload.draw_moneyline_american) {
                        hasBetbckMl = true;
                    }
                }
                if (!betbckOddsPayload || hasBetbckMl) { // Show header if no BetBCK data yet OR if BetBCK has some ML data
                    tableHtml += `<tr class="market-group"><td colspan="7">Moneyline (${periodName})</td></tr>`;
                }
                renderRow("Moneyline", homeTeam, '', ml.american_home, ml.nvp_american_home, 
                    (periodName.toLowerCase().includes("match") && betbckOddsPayload) ? betbckOddsPayload.home_moneyline_american : null);
                renderRow("Moneyline", awayTeam, '', ml.american_away, ml.nvp_american_away, 
                    (periodName.toLowerCase().includes("match") && betbckOddsPayload) ? betbckOddsPayload.away_moneyline_american : null);
                if (ml.american_draw !== undefined && ml.american_draw !== null && ml.american_draw !== 'N/A') {
                    renderRow("Moneyline", "Draw", '', ml.american_draw, ml.nvp_american_draw, 
                        (periodName.toLowerCase().includes("match") && betbckOddsPayload) ? betbckOddsPayload.draw_moneyline_american : null);
                }
            }

            // Spreads - Pinnacle provides an OBJECT of spreads
            if (currentPeriodData.spreads && typeof currentPeriodData.spreads === 'object' && !Array.isArray(currentPeriodData.spreads)) {
                const spreadsArray = Object.values(currentPeriodData.spreads);
                let hasBetbckSpreadsForPeriod = false;
                if (betbckOddsPayload && periodName.toLowerCase().includes("match")) { // Only check for main game spreads from BetBCK
                     if (spreadsArray.some(s => betbckOddsPayload.home_spreads?.find(bs => bs.line === (s.hdp > 0 ? `+${s.hdp}` : `${s.hdp}`))?.odds || 
                                                betbckOddsPayload.away_spreads?.find(bs => bs.line === (s.hdp === 0 ? "0" : (s.hdp > 0 ? `+${-s.hdp}` : `${-s.hdp}`)))?.odds )) {
                        hasBetbckSpreadsForPeriod = true;
                     }
                }
                if(!betbckOddsPayload || hasBetbckSpreadsForPeriod) {
                    if (spreadsArray.length > 0) tableHtml += `<tr class="market-group"><td colspan="7">Spreads (${periodName})</td></tr>`;
                }
                spreadsArray.forEach(s => { /* ... existing spread rendering logic ... */
                    if (typeof s !== 'object' || s.hdp === undefined) return;
                    const homeLineStr = s.hdp > 0 ? `+${s.hdp}` : `${s.hdp}`;
                    const awayLineVal = -s.hdp;
                    const awayLineStr = awayLineVal === 0 ? "0" : (awayLineVal > 0 ? `+${awayLineVal}` : `${awayLineVal}`);
                    let bckHomeSpread = null, bckAwaySpread = null;
                    if (betbckOddsPayload && periodName.toLowerCase().includes("match")) { // Only match BetBCK full game spreads
                        bckHomeSpread = betbckOddsPayload.home_spreads?.find(bs => bs.line === homeLineStr)?.odds;
                        bckAwaySpread = betbckOddsPayload.away_spreads?.find(bs => bs.line === awayLineStr)?.odds;
                    }
                    renderRow("Spread", homeTeam, homeLineStr, s.american_home, s.nvp_american_home, bckHomeSpread);
                    renderRow("Spread", awayTeam, awayLineStr, s.american_away, s.nvp_american_away, bckAwaySpread);
                });
            }

            // Totals - Pinnacle provides an OBJECT of totals
            if (currentPeriodData.totals && typeof currentPeriodData.totals === 'object' && !Array.isArray(currentPeriodData.totals)) {
                const totalsArray = Object.values(currentPeriodData.totals);
                let hasBetbckTotalsForPeriod = false;
                if (betbckOddsPayload && periodName.toLowerCase().includes("match")){
                    if (totalsArray.some(t => String(betbckOddsPayload.game_total_line) === String(t.points) && (betbckOddsPayload.game_total_over_odds || betbckOddsPayload.game_total_under_odds))) {
                        hasBetbckTotalsForPeriod = true;
                    }
                }
                if(!betbckOddsPayload || hasBetbckTotalsForPeriod){
                    if (totalsArray.length > 0) tableHtml += `<tr class="market-group"><td colspan="7">Totals (${periodName})</td></tr>`;
                }
                totalsArray.forEach(t => { /* ... existing total rendering logic ... */
                    if (typeof t !== 'object' || t.points === undefined) return;
                    const pointsStr = `${t.points}`;
                    let bckOverOdds = null, bckUnderOdds = null;
                    if (betbckOddsPayload && periodName.toLowerCase().includes("match") && String(betbckOddsPayload.game_total_line) === pointsStr) {
                        bckOverOdds = betbckOddsPayload.game_total_over_odds;
                        bckUnderOdds = betbckOddsPayload.game_total_under_odds;
                    }
                    renderRow("Total", "Over", pointsStr, t.american_over, t.nvp_american_over, bckOverOdds);
                    renderRow("Total", "Under", pointsStr, t.american_under, t.nvp_american_under, bckUnderOdds);
                });
            }
        }; // End appendMarketRows

        const period0 = pinnacleEventDetails.periods?.num_0;
        const period1 = pinnacleEventDetails.periods?.num_1;
        if (period0) appendMarketRows(period0, "Match");
        if (period1) appendMarketRows(period1, "1st Half"); // BetBCK odds will be null for 1H rows

        if (!period0 && !period1 && Object.keys(pinnacleEventDetails.periods || {}).length === 0) {
            tableHtml += '<tr><td colspan="7">No detailed period odds in Pinnacle data.</td></tr>';
        }
        tableHtml += '</tbody></table>';

        previousDataSnapshot[eventId] = {
            markets: newPinnacleMarketsSnapshot,
            pinnacleLastUpdateTs: pinnacleEventDetails?.last, // Use optional chaining
            alertArrivalTs: eventEntryFromServer.alert_arrival_timestamp,
            betbckStatus: betbckFullResponse?.status 
        };
        return tableHtml;
    } // End createTableForEvent

    async function fetchAndRefreshAllActiveEvents() { // Keep your latest working version (v7.8 logic)
        // ... (This function should be mostly fine from the v7.8 I provided, which handles:
        //      - Fetching /get_active_events_data
        //      - Sorting by alert_arrival_timestamp
        //      - Slicing by MAX_EVENTS_TO_DISPLAY
        //      - Managing displayedEventIdsOnPage
        //      - Building/Updating eventDivs
        //      - Reordering DOM if necessary
        //      - Error handling ) ...
        // The crucial part is that the eventEntryFromServer it passes to createTableForEvent
        // contains the alert_arrival_timestamp and the correct betbck_data structure.
        try {
            const response = await fetch(`http://localhost:5001/get_active_events_data`);
            if (!response.ok) { console.error(`HTTP error ${response.status}`); if (mainLoadingMessage) mainLoadingMessage.textContent = `Error fetching`; return; }
            const allEventsDataFromServer = await response.json();
            const sortedEventEntries = Object.entries(allEventsDataFromServer)
                .sort(([,a_entry],[,b_entry]) => (b_entry.alert_arrival_timestamp||0) - (a_entry.alert_arrival_timestamp||0))
                .slice(0, MAX_EVENTS_TO_DISPLAY);
            if(mainLoadingMessage){const noEvents=sortedEventEntries.length===0 && displayedEventIdsOnPage.size===0; mainLoadingMessage.style.display=noEvents?'block':'none'; if(noEvents)mainLoadingMessage.textContent="No active alerts. Waiting...";}
            const receivedEventIdsThisFetch = new Set(sortedEventEntries.map(([eventId,_])=>eventId));
            Array.from(oddsDisplayArea.children).forEach(childDiv => {
                const childId = childDiv.id.replace('event-container-','');
                if(!receivedEventIdsThisFetch.has(childId)){ childDiv.remove(); delete previousDataSnapshot[childId]; displayedEventIdsOnPage.delete(childId); }
            });
            const divsToRenderInOrder = [];
            for (const [eventId, eventEntry] of sortedEventEntries) {
                let eventDiv = document.getElementById(`event-container-${eventId}`);
                let needsFullRender = !eventDiv;
                if (!eventDiv) {
                    eventDiv = document.createElement('div'); eventDiv.className = 'event-container'; eventDiv.id = `event-container-${eventId}`;
                }
                const prevSnap = previousDataSnapshot[eventId];
                const currentPinTs = eventEntry.pinnacle_data_processed?.data?.last;
                const currentBckStatus = eventEntry.betbck_data?.status;
                if (!prevSnap || prevSnap.pinnacleLastUpdateTs !== currentPinTs || prevSnap.betbckStatus !== currentBckStatus || prevSnap.alertArrivalTs !== eventEntry.alert_arrival_timestamp) {
                    needsFullRender = true;
                }
                if (needsFullRender) {
                    eventDiv.innerHTML = createTableForEvent(eventId, eventEntry);
                    eventDiv.querySelectorAll('.odds-changed').forEach(cell => {
                        cell.classList.add('flash-yellow');
                        setTimeout(() => { cell.classList.remove('flash-yellow'); cell.classList.remove('odds-changed'); }, FLASH_DURATION_MS);
                    });
                }
                divsToRenderInOrder.push(eventDiv);
                 if (!displayedEventIdsOnPage.has(eventId)) { displayedEventIdsOnPage.add(eventId); }
            }
            // Smart re-ordering: only re-append if order changed or new divs added
            let currentDomOrder = Array.from(oddsDisplayArea.children);
            let domNeedsReorder = divsToRenderInOrder.length !== currentDomOrder.length;
            if (!domNeedsReorder) {
                for(let i=0; i < divsToRenderInOrder.length; i++) { if (!currentDomOrder[i] || currentDomOrder[i].id !== divsToRenderInOrder[i].id) { domNeedsReorder = true; break; } }
            }
            if (domNeedsReorder) {
                oddsDisplayArea.innerHTML = ''; // Clear
                divsToRenderInOrder.forEach(div => oddsDisplayArea.appendChild(div));
            }
        } catch (error) { console.error("[Realtime.js] Error refreshing:", error); if(mainLoadingMessage) mainLoadingMessage.textContent = `Error: ${error.message}`; }
    }
    
    if (mainLoadingMessage) mainLoadingMessage.textContent = "Fetching initial data...";
    fetchAndRefreshAllActiveEvents();
    setInterval(fetchAndRefreshAllActiveEvents, REFRESH_INTERVAL_MS);
});