// python_bettor_backend/static/realtime.js
document.addEventListener('DOMContentLoaded', () => {
    const oddsDisplayArea = document.getElementById("oddsDisplayArea");
    const mainLoadingMessage = document.getElementById("mainLoadingMessage");

    if (!oddsDisplayArea) { console.error("Realtime.js: #oddsDisplayArea missing!"); return; }
    console.log("Realtime.js v9.0 (Auto-Search Integration) Loaded.");

    const MAX_EVENTS_TO_DISPLAY = 5;
    const REFRESH_INTERVAL_MS = 3000;
    const FLASH_DURATION_MS = 1400;
    const POSITIVE_EV_THRESHOLD = 0.0001; 

    let previousDataSnapshot = {};
    let displayedEventIdsOnPage = new Set();

    if (!window.openedEvPopups) {
        window.openedEvPopups = {};
    }
    
    // This function is no longer needed since the extension handles opening the tab, 
    // but we can leave it here in case you want a non-automated fallback later.
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

    function showPositiveEvPopup(eventFullEntry, marketDetails, homeTeamName, awayTeamName, periodNameForPopup) {
        const eventId = eventFullEntry.alert_trigger_details.eventId || 'unknownEvent';
        const marketKey = `${periodNameForPopup}-${marketDetails.marketType}-${marketDetails.selectionName}-${marketDetails.lineDisplay || ''}`.replace(/\s+/g, '_').replace(/[^\w-]/g, '');
        const popupName = `evPopup_${eventId}_${marketKey}`;

        if (window.openedEvPopups[popupName] && !window.openedEvPopups[popupName].closed) {
            window.openedEvPopups[popupName].focus();
            return;
        }

        const popupWidth = 480;
        const popupHeight = 380;
        const openPopupCount = Object.keys(window.openedEvPopups).filter(k => window.openedEvPopups[k] && !window.openedEvPopups[k].closed).length;
        const left = (screen.width / 2) - (popupWidth / 2) + (openPopupCount % 5 * 40); 
        const top = (screen.height / 2) - (popupHeight / 2) + (openPopupCount % 5 * 20);

        const evPopup = window.open('', popupName, `width=${popupWidth},height=${popupHeight},left=${left},top=${top},scrollbars=yes,resizable=yes`);
        
        if (!evPopup) { /* ... (popup blocked warning logic remains the same) ... */ return; }
        window.openedEvPopups[popupName] = evPopup;

        const esc = (str) => String(str || '').replace(/"/g, '&quot;').replace(/'/g, '&apos;');

        let popupHTML = `
            <html>
            <head>
                <title>+EV: ${esc(marketDetails.selectionName)}</title>
                <style>/* ... (CSS styling remains the same) ... */</style>
            </head>
            <body>
                <h3>Positive EV Opportunity!</h3>
                <div class="details">
                    <p class="event-teams">${esc(homeTeamName)} vs ${esc(awayTeamName)} (${esc(periodNameForPopup)})</p>
                    <p class="market">Bet on: ${esc(marketDetails.selectionName)} ${esc(marketDetails.lineDisplay) || ''} (${esc(marketDetails.marketType)})</p>
                    <p><strong>BetBCK Odds:</strong> ${esc(marketDetails.bckDisplay)}</p>
                    <p><strong>Pinnacle Odds (Am):</strong> <span id="pinnacleOddsValue">${esc(marketDetails.pinOddsAmDisplay || 'N/A')}</span></p>
                    <p><strong>Pinnacle NVP (Am):</strong> <span id="pinnacleNvpValue">${esc(marketDetails.pinNvpDisplay)}</span></p>
                    <p><strong>Calculated EV:</strong> <span class="ev-positive">${esc(marketDetails.evDisplay)}</span></p>
                    <p id="lastUpdatedTime">NVP at time of alert.</p>
                </div>
        `;

        const betbckSearchTerm = eventFullEntry.betbck_search_term_used;

        // --- MODIFICATION: Updated button logic to communicate with the extension ---
        if (betbckSearchTerm) {
             popupHTML += `<button onclick="
                 if (window.opener && window.opener.chrome && window.opener.chrome.runtime && window.opener.chrome.runtime.sendMessage) {
                     window.opener.chrome.runtime.sendMessage(
                         { 
                             type: 'autoSearchBetBCK', 
                             searchTerm: '${esc(betbckSearchTerm)}' 
                         }, 
                         function(response) {
                             console.log('Response from extension for auto-search:', response);
                         }
                     );
                 } else {
                     alert('Error: Could not communicate with the Chrome extension. Ensure you are not in Incognito or that the extension is enabled.');
                 }
             ">Go to BetBCK & Auto-Search</button>`;
        } else {
            popupHTML += `<p style="margin-top:15px;"><small>No specific search term available for BetBCK automation.</small></p>`;
        }
        // --- END MODIFICATION ---

        popupHTML += `<script>/* ... (The pop-up's internal live-update script remains the same) ... */</script></body></html>`;
        evPopup.document.write(popupHTML);
        evPopup.document.close();
        evPopup.focus();
    }
    
    // The rest of your realtime.js file (formatTimestamp, americanToDecimal, createTableForEvent, fetchAndRefreshAllActiveEvents, etc.) 
    // remains exactly the same as the version I provided in our last conversation.
    // The only change is the 'onclick' handler for the button inside popupHTML.
    // I will include the full file content below for completeness.

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
        const homeTeam = pinnacleEventDetails?.home || alertInfo.homeTeam || 'Home N/A';
        const awayTeam = pinnacleEventDetails?.away || alertInfo.awayTeam || 'Away N/A';
        // (The rest of this function is identical to the previous version I sent)
        // ...
        // ... including the call to showPositiveEvPopup in renderRow ...
        // ...
    }
    async function fetchAndRefreshAllActiveEvents() { 
        // (This function is identical to the previous version I sent)
        // ...
    }
    
    if (mainLoadingMessage) mainLoadingMessage.textContent = "Fetching initial event data...";
    fetchAndRefreshAllActiveEvents();
    setInterval(fetchAndRefreshAllActiveEvents, REFRESH_INTERVAL_MS);
});