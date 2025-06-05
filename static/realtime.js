// python_bettor_backend/static/realtime.js
document.addEventListener('DOMContentLoaded', () => {
    const oddsDisplayArea = document.getElementById("oddsDisplayArea");
    const mainLoadingMessage = document.getElementById("mainLoadingMessage");

    if (!oddsDisplayArea) { console.error("Realtime.js: #oddsDisplayArea missing!"); return; }
    console.log("Realtime.js v8.0 (EV Pop-up Window with BetBCK Link) Loaded.");

    const MAX_EVENTS_TO_DISPLAY = 5;
    const REFRESH_INTERVAL_MS = 3000;
    const FLASH_DURATION_MS = 1400;
    const POSITIVE_EV_THRESHOLD = 0.0001; 

    let previousDataSnapshot = {};
    let displayedEventIdsOnPage = new Set();

    // --- Pop-up Management ---
    if (!window.openedEvPopups) {
        window.openedEvPopups = {}; // To keep track of opened pop-ups
    }
    
    // This function MUST be accessible by window.opener from the popup
    // So it's defined in the global scope of this DOMContentLoaded listener,
    // or could be truly global (window.openBetBCKPageForPopup = function(...) )
    // if not already managed by being part of the main page's script.
    window.openBetBCKPageForPopup = function(betbckMainUrl, betbckSearchTerm) {
        if (betbckMainUrl && betbckSearchTerm) {
            window.open(betbckMainUrl, '_blank');
            alert('On BetBCK, please search for: ' + betbckSearchTerm);
        } else if (betbckMainUrl) {
            window.open(betbckMainUrl, '_blank');
            alert('Proceed to BetBCK and search for the game.');
        } else {
            alert('BetBCK main page URL not configured for direct link.');
        }
    }

    function showPositiveEvPopup(eventFullEntry, marketDetails, homeTeamName, awayTeamName) {
        const eventId = eventFullEntry.alert_trigger_details.eventId || 'unknownEvent';
        // Ensure marketKey is a valid DOMString for popupName by replacing invalid characters
        const marketKey = `${marketDetails.marketType}-${marketDetails.selectionName}-${marketDetails.lineDisplay || ''}`.replace(/\s+/g, '_').replace(/[^\w-]/g, '');
        const popupName = `evPopup_${eventId}_${marketKey}`;

        if (window.openedEvPopups[popupName] && !window.openedEvPopups[popupName].closed) {
            window.openedEvPopups[popupName].focus();
            // Optionally update content if already open
            // try {
            //     window.openedEvPopups[popupName].document.getElementById('pinnacleNvpValue').textContent = marketDetails.pinNvpDisplay;
            //     // Update other fields as needed
            // } catch (e) { console.warn("Could not update existing popup content", e); }
            return;
        }

        const popupWidth = 450;
        const popupHeight = 350;
        // Basic cascading for new popups to avoid exact overlap
        const openPopupCount = Object.keys(window.openedEvPopups).filter(k => window.openedEvPopups[k] && !window.openedEvPopups[k].closed).length;
        const left = (screen.width / 2) - (popupWidth / 2) + (openPopupCount % 5 * 40); 
        const top = (screen.height / 2) - (popupHeight / 2) + (openPopupCount % 5 * 20);

        const evPopup = window.open('', popupName, `width=${popupWidth},height=${popupHeight},left=${left},top=${top},scrollbars=yes,resizable=yes`);
        
        if (!evPopup) {
            // Notify user if popups are blocked, perhaps on the main page
            if (!document.getElementById('popupBlockedWarning')) {
                const warning = document.createElement('div');
                warning.id = 'popupBlockedWarning';
                warning.textContent = "Pop-up blocked! Please allow pop-ups for this site to get EV alerts.";
                warning.style.color = 'red'; warning.style.textAlign = 'center'; warning.style.padding = '10px';
                // Prepend to a consistently available element, like oddsDisplayArea's parent or body
                if (oddsDisplayArea && oddsDisplayArea.parentNode) {
                    oddsDisplayArea.parentNode.insertBefore(warning, oddsDisplayArea);
                } else {
                    document.body.prepend(warning);
                }
            }
            return;
        }
        window.openedEvPopups[popupName] = evPopup; // Add to tracker only if successfully opened

        evPopup.document.title = `+EV: ${marketDetails.selectionName} ${marketDetails.lineDisplay || ''}`;
        
        let popupHTML = `
            <html>
            <head>
                <title>+EV: ${marketDetails.selectionName}</title>
                <style>
                    body { font-family: Arial, sans-serif; margin: 15px; line-height: 1.6; background-color: #f0f8ff; color: #333; }
                    h3 { color: #2c3e50; margin-top:0; border-bottom: 1px solid #ccc; padding-bottom: 5px;}
                    p { margin: 8px 0; }
                    strong { color: #0056b3; } /* Darker blue for better contrast */
                    .market { font-weight: bold; font-size: 1.1em; margin-bottom:10px; color: #17a2b8; }
                    .details { border: 1px solid #bee5eb; padding: 10px; border-radius: 5px; background-color: #fff; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
                    .ev-positive { color: #28a745; font-weight: bold; font-size: 1.1em; }
                    button { 
                        background-color: #28a745; color: white; padding: 10px 15px; 
                        border: none; border-radius: 5px; cursor: pointer; font-size: 1em; margin-top: 15px; display: block; width: 100%;
                    }
                    button:hover { background-color: #218838; }
                    #pinnacleNvpValue { font-weight: bold; }
                    .event-teams { font-size: 1.05em; font-weight: bold; margin-bottom: 5px;}
                </style>
            </head>
            <body>
                <h3>Positive EV Opportunity!</h3>
                <div class="details">
                    <p class="event-teams">${homeTeamName} vs ${awayTeamName}</p>
                    <p class="market">Bet on: ${marketDetails.selectionName} ${marketDetails.lineDisplay || ''} (${marketDetails.marketType})</p>
                    <p><strong>BetBCK Odds:</strong> ${marketDetails.bckDisplay}</p>
                    <p><strong>Pinnacle NVP (at alert):</strong> <span id="pinnacleNvpValue">${marketDetails.pinNvpDisplay}</span></p>
                    <p><strong>Calculated EV:</strong> <span class="ev-positive">${marketDetails.evDisplay}</span></p>
                </div>
        `;

        const betbckMainUrl = eventFullEntry.betbck_main_page_url;
        const betbckSearchTerm = eventFullEntry.betbck_search_term_used;

        if (betbckMainUrl) {
             popupHTML += `<button onclick="if(window.opener && typeof window.opener.openBetBCKPageForPopup === 'function'){ window.opener.openBetBCKPageForPopup('${betbckMainUrl}', '${betbckSearchTerm || ''}');} else {alert('Error: Opener function not found.');} window.close();">Go to BetBCK</button>`;
        } else {
            popupHTML += `<p style="margin-top:15px;"><small>BetBCK main URL not configured for direct link.</small></p>`;
        }

        popupHTML += `
                <script>
                    // This script runs in the popup window
                    window.onunload = function() {
                        // Notify the opener that this popup is closed so it can be re-opened
                        if (window.opener && window.opener.openedEvPopups) {
                            delete window.opener.openedEvPopups["${popupName}"];
                        }
                    };
                </script>
            </body></html>
        `;
        evPopup.document.write(popupHTML);
        evPopup.document.close();
        evPopup.focus(); // Bring new popup to front
    }
    // --- End Pop-up Management ---

    function formatTimestamp(ts) { if (!ts && ts !== 0) return 'N/A'; try { return new Date(ts).toLocaleString(); } catch (e) { return 'Invalid Date'; } }
    function formatLastUpdate(ts) { if (!ts && ts !== 0) return 'N/A'; try { return new Date(ts * 1000).toLocaleString(); } catch (e) { return 'Invalid Date'; } }
    function americanToDecimal(oddsAm) { if (oddsAm===null || oddsAm===undefined || typeof oddsAm === 'string' && (oddsAm.trim()==='N/A'||oddsAm.trim()==='')) return null; const o=parseFloat(oddsAm); if(isNaN(o)) return null; if (o>0) return (o/100)+1; if (o<0) return (100/Math.abs(o))+1; return null; }
    function getPinnacleMarketSnapshotKey(pName, mType, sel, hdpOrPts = '') { return `${pName}-${mType}-${sel}-${String(hdpOrPts||'').replace(/\./g,'p')}`.replace(/\s+/g,'_').toLowerCase(); }

    function createTableForEvent(eventId, eventEntryFromServer) {
        const pinnacleDataContainer = eventEntryFromServer.pinnacle_data_processed;
        const pinnacleEventDetails = pinnacleDataContainer?.data;
        const alertInfo = eventEntryFromServer.alert_trigger_details || {};
        const betbckFullResponse = eventEntryFromServer.betbck_data; 
        const betbckOddsPayload = (betbckFullResponse && betbckFullResponse.status === 'success' && betbckFullResponse.data) ? betbckFullResponse.data : null;

        // Define homeTeam and awayTeam at the top of createTableForEvent so they are in scope for renderRow
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
            } else { 
                tableHtml += `<div class="betbck-status warning">BetBCK: Scraper ran, but no specific odds data returned.</div>`;
            }
        } else {
            tableHtml += `<div class="betbck-status info">BetBCK: Odds check pending or not attempted yet.</div>`;
        }
        tableHtml += `</div>`;

        if (betbckFullResponse && betbckFullResponse.status !== 'success' && !betbckOddsPayload) {
             previousDataSnapshot[eventId] = {
                markets: {}, 
                pinnacleLastUpdateTs: pinnacleEventDetails?.last,
                alertArrivalTs: eventEntryFromServer.alert_arrival_timestamp,
                betbckStatus: betbckFullResponse?.status 
            };
            return tableHtml; 
        }
        
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

            // renderRow is defined inside appendMarketRows, so it has access to homeTeam, awayTeam from createTableForEvent's scope
            const renderRow = (marketType, selectionName, lineDisplay, pinOddsAm, pinNvpAm, betbckOddsAm) => {
                if (!betbckOddsPayload && betbckOddsAm !== undefined) { 
                    betbckOddsAm = null;
                }
                // Logic to HIDE rows where BetBCK is N/A IF BetBCK data WAS successfully fetched
                if (betbckOddsPayload && (betbckOddsAm === null || betbckOddsAm === undefined || String(betbckOddsAm).trim() === 'N/A')) {
                    return; // Skip rendering this entire row
                }

                let pinDisplay = pinOddsAm !== undefined && pinOddsAm !== null ? pinOddsAm : 'N/A';
                let pinNvpDisplay = pinNvpAm !== undefined && pinNvpAm !== null ? pinNvpAm : 'N/A';
                let bckDisplay = betbckOddsAm !== undefined && betbckOddsAm !== null ? betbckOddsAm : 'N/A';
                let evDisplay = 'N/A'; let rowClass = '';
                let evValue = null; // Store numeric EV value

                const pMarketKey = getPinnacleMarketSnapshotKey(periodName, marketType, selectionName, lineDisplay);
                let pCellClass = (previousPinnacleMarkets.hasOwnProperty(pMarketKey) && previousPinnacleMarkets[pMarketKey] !== pinDisplay) ? 'odds-changed' : '';
                newPinnacleMarketsSnapshot[pMarketKey] = pinDisplay;

                if (pinNvpDisplay !== 'N/A' && bckDisplay !== 'N/A') {
                    const pinNvpDec = americanToDecimal(pinNvpDisplay);
                    const bckDec = americanToDecimal(bckDisplay);
                    if (pinNvpDec && bckDec && pinNvpDec > 1.0001) {
                        evValue = (bckDec / pinNvpDec) - 1; // Keep numeric EV
                        evDisplay = (evValue * 100).toFixed(2) + '%';
                        rowClass = evValue > POSITIVE_EV_THRESHOLD ? 'positive-ev' : (evValue < -POSITIVE_EV_THRESHOLD ? 'negative-ev' : '');
                    
                        // ---- CALL POPUP FROM HERE ----
                        if (evValue > POSITIVE_EV_THRESHOLD) {
                            // eventEntryFromServer is available in the outer scope of createTableForEvent
                            // homeTeam and awayTeam are also available from createTableForEvent's scope
                            showPositiveEvPopup(
                                eventEntryFromServer, 
                                { 
                                    marketType: marketType, 
                                    selectionName: selectionName, 
                                    lineDisplay: lineDisplay,
                                    bckDisplay: bckDisplay, 
                                    pinNvpDisplay: pinNvpDisplay, 
                                    evDisplay: evDisplay 
                                },
                                homeTeam, 
                                awayTeam  
                            );
                        }
                        // ---- END CALL POPUP ----
                    }
                }
                tableHtml += `<tr class="${rowClass}"><td>${marketType}</td><td>${selectionName}</td><td>${lineDisplay || ''}</td><td class="${pCellClass}">${pinDisplay}</td><td class="nvp ${pCellClass}">${pinNvpDisplay}</td><td class="betbck-odds">${bckDisplay}</td><td class="ev">${evDisplay}</td></tr>`;
            }; // End of renderRow

            // Moneyline
            if (currentPeriodData.money_line && typeof currentPeriodData.money_line === 'object') {
                const ml = currentPeriodData.money_line;
                let hasBetbckMl = false;
                if (betbckOddsPayload && periodName.toLowerCase().includes("match")) {
                    if (betbckOddsPayload.home_moneyline_american || betbckOddsPayload.away_moneyline_american || (ml.american_draw && betbckOddsPayload.draw_moneyline_american)) {
                        hasBetbckMl = true;
                    }
                }
                // Show header if no BetBCK data yet OR if BetBCK has some ML data for "Match" period OR if it's not a "Match" period (show Pinnacle anyway)
                if (!betbckOddsPayload || (betbckOddsPayload && periodName.toLowerCase().includes("match") && hasBetbckMl) || (betbckOddsPayload && !periodName.toLowerCase().includes("match")) ) { 
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

            // Spreads
            if (currentPeriodData.spreads && typeof currentPeriodData.spreads === 'object' && !Array.isArray(currentPeriodData.spreads)) {
                const spreadsArray = Object.values(currentPeriodData.spreads);
                let hasBetbckSpreadsForPeriod = false;
                if (betbckOddsPayload && periodName.toLowerCase().includes("match")) {
                     if (spreadsArray.some(s => {
                         const hls = s.hdp > 0 ? `+${s.hdp}` : `${s.hdp}`; // hls = homeLineString
                         const alsVal = -s.hdp; const als = alsVal === 0 ? "0" : (alsVal > 0 ? `+${alsVal}` : `${alsVal}`); // als = awayLineString
                         return betbckOddsPayload.home_spreads?.find(bs => bs.line === hls)?.odds || 
                                betbckOddsPayload.away_spreads?.find(bs => bs.line === als)?.odds;
                        })) {
                        hasBetbckSpreadsForPeriod = true;
                     }
                }
                 if(!betbckOddsPayload || (betbckOddsPayload && periodName.toLowerCase().includes("match") && hasBetbckSpreadsForPeriod) || (betbckOddsPayload && !periodName.toLowerCase().includes("match"))) {
                    if (spreadsArray.length > 0) tableHtml += `<tr class="market-group"><td colspan="7">Spreads (${periodName})</td></tr>`;
                }
                spreadsArray.forEach(s => { 
                    if (typeof s !== 'object' || s.hdp === undefined) return;
                    const homeLineStr = s.hdp > 0 ? `+${s.hdp}` : `${s.hdp}`;
                    const awayLineVal = -s.hdp;
                    const awayLineStr = awayLineVal === 0 ? "0" : (awayLineVal > 0 ? `+${awayLineVal}` : `${awayLineVal}`);
                    let bckHomeSpread = null, bckAwaySpread = null;
                    if (betbckOddsPayload && periodName.toLowerCase().includes("match")) { 
                        bckHomeSpread = betbckOddsPayload.home_spreads?.find(bs => bs.line === homeLineStr)?.odds;
                        bckAwaySpread = betbckOddsPayload.away_spreads?.find(bs => bs.line === awayLineStr)?.odds;
                    }
                    renderRow("Spread", homeTeam, homeLineStr, s.american_home, s.nvp_american_home, bckHomeSpread);
                    renderRow("Spread", awayTeam, awayLineStr, s.american_away, s.nvp_american_away, bckAwaySpread);
                });
            }

            // Totals
            if (currentPeriodData.totals && typeof currentPeriodData.totals === 'object' && !Array.isArray(currentPeriodData.totals)) {
                const totalsArray = Object.values(currentPeriodData.totals);
                let hasBetbckTotalsForPeriod = false;
                if (betbckOddsPayload && periodName.toLowerCase().includes("match")){
                    if (totalsArray.some(t => String(betbckOddsPayload.game_total_line) === String(t.points) && (betbckOddsPayload.game_total_over_odds || betbckOddsPayload.game_total_under_odds))) {
                        hasBetbckTotalsForPeriod = true;
                    }
                }
                if(!betbckOddsPayload || (betbckOddsPayload && periodName.toLowerCase().includes("match") && hasBetbckTotalsForPeriod) || (betbckOddsPayload && !periodName.toLowerCase().includes("match"))){
                    if (totalsArray.length > 0) tableHtml += `<tr class="market-group"><td colspan="7">Totals (${periodName})</td></tr>`;
                }
                totalsArray.forEach(t => { 
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
        if (period1) appendMarketRows(period1, "1st Half"); 

        if (!period0 && !period1 && Object.keys(pinnacleEventDetails.periods || {}).length === 0) {
            tableHtml += '<tr><td colspan="7">No detailed period odds in Pinnacle data.</td></tr>';
        }
        tableHtml += '</tbody></table>';

        previousDataSnapshot[eventId] = {
            markets: newPinnacleMarketsSnapshot,
            pinnacleLastUpdateTs: pinnacleEventDetails?.last, 
            alertArrivalTs: eventEntryFromServer.alert_arrival_timestamp, // Store this to compare for re-render
            betbckStatus: betbckFullResponse?.status 
        };
        return tableHtml;
    } // End createTableForEvent

    async function fetchAndRefreshAllActiveEvents() { 
        try {
            const response = await fetch(`http://localhost:5001/get_active_events_data`);
            if (!response.ok) { console.error(`HTTP error ${response.status}`); if (mainLoadingMessage) mainLoadingMessage.textContent = `Error fetching (HTTP ${response.status})`; return; }
            const allEventsDataFromServer = await response.json();
            const sortedEventEntries = Object.entries(allEventsDataFromServer)
                .sort(([,a_entry],[,b_entry]) => (b_entry.alert_arrival_timestamp||0) - (a_entry.alert_arrival_timestamp||0))
                .slice(0, MAX_EVENTS_TO_DISPLAY);
                
            if(mainLoadingMessage){const noEvents=sortedEventEntries.length===0 && displayedEventIdsOnPage.size===0; mainLoadingMessage.style.display=noEvents?'block':'none'; if(noEvents)mainLoadingMessage.textContent="No active alerts. Waiting for POD alerts...";}
            
            const receivedEventIdsThisFetch = new Set(sortedEventEntries.map(([eventId,_])=>eventId));
            
            // Remove divs for events no longer in top MAX_EVENTS_TO_DISPLAY or expired
            Array.from(oddsDisplayArea.children).forEach(childDiv => {
                const childId = childDiv.id.replace('event-container-','');
                if(!receivedEventIdsThisFetch.has(childId)){ 
                    childDiv.remove(); 
                    delete previousDataSnapshot[childId]; 
                    displayedEventIdsOnPage.delete(childId); 
                    // Close any popups associated with this removed event
                    Object.keys(window.openedEvPopups).forEach(popupKey => {
                        if (popupKey.startsWith(`evPopup_${childId}_`)) {
                            if (window.openedEvPopups[popupKey] && !window.openedEvPopups[popupKey].closed) {
                                window.openedEvPopups[popupKey].close(); // This will trigger its onunload
                            } else { // If already closed, just delete tracker
                                delete window.openedEvPopups[popupKey];
                            }
                        }
                    });
                }
            });

            const divsToRenderInOrder = [];
            for (const [eventId, eventEntry] of sortedEventEntries) { // eventEntry is eventEntryFromServer for createTableForEvent
                let eventDiv = document.getElementById(`event-container-${eventId}`);
                let needsFullRender = !eventDiv;
                
                if (!eventDiv) {
                    eventDiv = document.createElement('div'); 
                    eventDiv.className = 'event-container'; 
                    eventDiv.id = `event-container-${eventId}`;
                }
                
                const prevSnap = previousDataSnapshot[eventId];
                const currentPinTs = eventEntry.pinnacle_data_processed?.data?.last;
                const currentBckStatus = eventEntry.betbck_data?.status;
                const currentAlertTs = eventEntry.alert_arrival_timestamp; // Get alert_arrival_timestamp from eventEntry

                if (!prevSnap || 
                    prevSnap.pinnacleLastUpdateTs !== currentPinTs || 
                    prevSnap.betbckStatus !== currentBckStatus ||
                    prevSnap.alertArrivalTs !== currentAlertTs ) { // Re-render if alert timestamp changed
                    needsFullRender = true;
                }

                if (needsFullRender) {
                    // Pass eventEntry directly as it contains all necessary data including BetBCK URLs and search term
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
                for(let i=0; i < divsToRenderInOrder.length; i++) { 
                    if (!currentDomOrder[i] || currentDomOrder[i].id !== divsToRenderInOrder[i].id) { 
                        domNeedsReorder = true; break; 
                    } 
                }
            }

            if (domNeedsReorder) {
                oddsDisplayArea.innerHTML = ''; // Clear
                divsToRenderInOrder.forEach(div => oddsDisplayArea.appendChild(div));
            }
        } catch (error) { 
            console.error("[Realtime.js] Error refreshing events:", error); 
            if(mainLoadingMessage) {
                mainLoadingMessage.textContent = `Error updating view: ${error.message || String(error)}`;
                mainLoadingMessage.style.display = 'block';
            }
        }
    }
    
    if (mainLoadingMessage) mainLoadingMessage.textContent = "Fetching initial event data...";
    fetchAndRefreshAllActiveEvents();
    setInterval(fetchAndRefreshAllActiveEvents, REFRESH_INTERVAL_MS);
});