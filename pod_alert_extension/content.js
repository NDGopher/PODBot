// pod_alert_extension/content.js
// BASED ON YOUR WORKING VERSION THAT YOU PROVIDED
// Changes:
// 1. Ensure 'waitForEventId' correctly interfaces with 'background.js' for the SNIFFED Swordfish eventId.
// 2. Ensure 'processAlert' sends the CORRECT eventId in the payload to 'background.js'.

(function() {
    console.log("POD Content Script (Your Working Base - v5 EventId Focus) Loaded:", new Date().toISOString());

    if (!window.location.pathname.endsWith('/terminal')) {
        console.log("Not on /terminal, POD Content Script exiting.");
        return;
    }

    const processedAlerts = new Map(); 
    const FETCH_INTERVAL = 2000; // Your original value
    let lastFetchTime = 0;      

    function waitForElement(selector, timeout = 15000, parentNode = document.body) {
        return new Promise((resolve) => {
            let element = parentNode.querySelector(selector);
            if (element) { resolve(element); return; }
            const observer = new MutationObserver((_, obs) => {
                element = parentNode.querySelector(selector);
                if (element) { obs.disconnect(); resolve(element); }
            });
            observer.observe(parentNode, { childList: true, subtree: true });
            setTimeout(() => {
                observer.disconnect();
                resolve(parentNode.querySelector(selector));
            }, timeout);
        });
    }

    function generateAlertHash(alertData) { // Your original
        return `${alertData["Home Team"]}-${alertData["Away Team"]}-${alertData["OldOdds"]}-${alertData["NewOdds"]}-${alertData["Bet"]}-${alertData["LineType"]}`;
    }

    function parseMatchString(matchStr) { // Your original
        try {
            const parts = matchStr.split('H:');
            if (parts.length < 2) return null;
            const timeDate = parts[0].trim();
            const timeDateParts = timeDate.split(' ');
            const time = timeDateParts[0] || "";
            const date = timeDateParts[1] || "";
            const remaining = parts[1].split('A:');
            if (remaining.length < 2) return null;
            const homeTeam = remaining[0].trim();
            let awayTeamAndLeague = remaining[1].trim();
            let league = "Unknown";
            let awayTeam = awayTeamAndLeague;

            const knownLeagues = ["NCAA", "NBA", "NHL", "MLB", "Copa Do Nordeste", "Brazil - Cup", "Qatar - Emir Cup", "Kenya - Premier League"]; // Added from your logs
            for (const knownLeague of knownLeagues) {
                // More robust check: ensure knownLeague is a whole word or at the end
                const regex = new RegExp(`\\b${knownLeague.replace(/[-\/\\^$*+?.()|[\]{}]/g, '\\$&')}\\b`, 'i'); // Case insensitive, whole word
                const match = awayTeamAndLeague.match(regex);
                if (match) {
                    const index = match.index;
                    // Check if it makes sense as a league (e.g., often towards the end)
                    if (index > awayTeamAndLeague.length / 2 || awayTeamAndLeague.substring(index + knownLeague.length).trim().length < 5) {
                         league = awayTeamAndLeague.substring(index, index + knownLeague.length);
                         awayTeam = awayTeamAndLeague.substring(0, index).trim();
                         break;
                    }
                }
            }
            if (league === "Unknown") { // Fallback
                const lastDashIndex = awayTeamAndLeague.lastIndexOf(" - ");
                if (lastDashIndex !== -1 && lastDashIndex > 0) { // Ensure dash is not at the beginning
                    let potentialLeague = awayTeamAndLeague.substring(lastDashIndex + 3).trim();
                    let potentialTeam = awayTeamAndLeague.substring(0, lastDashIndex).trim();
                    // Basic heuristic: if "league" part is shorter or contains typical league words
                    if (potentialLeague.length < potentialTeam.length || potentialLeague.toLowerCase().includes("league") || potentialLeague.toLowerCase().includes("cup")) {
                        league = potentialLeague;
                        awayTeam = potentialTeam;
                    } else {
                        // Keep awayTeam as is, league remains Unknown or is part of awayTeam
                    }
                }
            }
             if (awayTeam === league) awayTeam = awayTeamAndLeague.replace(league, "").trim();


            return { time, date, homeTeam, awayTeam, league };
        } catch (error) {
            console.error("Error parsing match string:", error, "Input:", matchStr);
            return { time:"N/A", date:"N/A", homeTeam:"N/A", awayTeam:"N/A", league:"N/A"};
        }
    }

    function extractAlertData(row) { // Your original (with slight robustification)
        try {
            const rowId = row.getAttribute("row-id");
            if (!rowId) return null;
            
            const eventIdFromRow = rowId.split('-')[0]; // Keep this as a fallback reference

            const matchCell = row.querySelector('div[col-id="match"]');
            const alertCell = row.querySelector('div[col-id="alert"]');
            const outcomeCell = row.querySelector('div[col-id="rowOutcome"]');
            const noVigPriceCell = row.querySelector('div[col-id="noVigPrice"]');
            const priceCell = row.querySelector('div[col-id="current"]');

            if (!matchCell || !alertCell || !outcomeCell || !priceCell || !noVigPriceCell) {
                 console.warn(`[extractAlertData] Missing one or more cells for rowId ${rowId}`); return null;
            }
            
            const matchData = parseMatchString(matchCell.textContent.trim());
            if (!matchData) { console.warn(`[extractAlertData] Failed to parse matchData for rowId ${rowId}`); return null; }

            const alertPTags = alertCell.querySelectorAll('p');
            let alertType = alertPTags[0]?.textContent.trim() || "N/A";
            let alertTimeElement = alertPTags[1]?.querySelector('time');
            let alertTime = alertTimeElement?.getAttribute('title') || alertTimeElement?.textContent.trim() || alertPTags[1]?.textContent.trim() || "N/A";
            
            const outcomePTags = outcomeCell.querySelectorAll('p');
            let period = outcomePTags[0]?.textContent.trim() || "N/A";
            let teamInBet = outcomePTags[1]?.textContent.trim() || "N/A"; 
            let lineValue = outcomePTags[2]?.textContent.trim() || ""; 
            
            let betDescription = `${teamInBet} ${lineValue}`.trim();
            let marketType = "Unknown";
            let teamForBetOnly = teamInBet; // For clarity

            const lowerTeamInBet = teamInBet.toLowerCase();
            if (lowerTeamInBet.startsWith("over ") || lowerTeamInBet.startsWith("under ")) { // Note the space
                marketType = "Total";
                const parts = teamInBet.split(" "); 
                teamForBetOnly = parts[0]; // "Over" or "Under"
                lineValue = parts.length > 1 ? parts.slice(1).join(" ") : lineValue; 
                betDescription = `${teamForBetOnly} ${lineValue}`;
            } else if (lineValue && (lineValue.startsWith('+') || lineValue.startsWith('-') || !isNaN(parseFloat(lineValue)))) {
                marketType = "Spread";
            } else if (teamInBet !== "N/A") { 
                marketType = "Moneyline";
                lineValue = ""; 
                betDescription = teamInBet;
            }
            
            let oldOdds = priceCell.querySelectorAll('span')[0]?.textContent.trim() || "N/A";
            let newOdds = priceCell.querySelectorAll('span')[1]?.textContent.trim() || "N/A";
            let noVigPrice = noVigPriceCell.querySelector('span')?.textContent.trim() || noVigPriceCell.textContent.trim() || "N/A";

            return {
                rowId: rowId, 
                eventIdFromRowAttribute: eventIdFromRow, // Store the one from row-id for reference
                eventId: null,                           // This is the one we REALLY want from sniffing
                timestamp: new Date().toISOString(), time: matchData.time, date: matchData.date, 
                homeTeam: matchData.homeTeam, awayTeam: matchData.awayTeam, league: matchData.league, 
                alertType: alertType, alertTime: alertTime, period: period, 
                teamForBet: teamForBetOnly, lineValueForBet: lineValue, betDescription: betDescription, 
                marketType: marketType, oldOdds: oldOdds, newOdds: newOdds, noVigPriceFromAlert: noVigPrice
            };
        } catch (error) { console.error("Error in extractAlertData:", error); return null; }
    }

    // --- YOUR ORIGINAL waitForEventId, but now calls getLatestSniffedEventDetails ---
    async function waitForSniffedEventId(clickTimestamp) {
        console.log(`[waitForSniffedEventId] Waiting for eventId from background after click at ${clickTimestamp}`);
        return new Promise((resolve) => {
            setTimeout(() => {
                let attempts = 0;
                const maxAttempts = 25; 
                const checkIntervalMs = 200;
                const intervalId = setInterval(() => {
                    attempts++;
                    chrome.runtime.sendMessage({ type: "getLatestSniffedEventDetails" }, response => { // Changed message type
                        if (chrome.runtime.lastError) {
                            // console.warn(`[waitForSniffedEventId] Attempt ${attempts}: Error:`, chrome.runtime.lastError.message);
                        }
                        if (response && response.eventId && response.timestamp && response.timestamp >= clickTimestamp) {
                            console.log(`[waitForSniffedEventId] SUCCESS (Attempt ${attempts}): Got sniffed EventID: ${response.eventId} (TS: ${response.timestamp}) from URL: ${response.url}`);
                            clearInterval(intervalId);
                            resolve(response.eventId);
                        } else if (attempts >= maxAttempts) {
                            console.warn(`[waitForSniffedEventId] TIMEOUT: No fresh sniffed eventId after ${attempts} attempts for click at ${clickTimestamp}. Last from BG:`, response);
                            clearInterval(intervalId);
                            resolve(null);
                        }
                    });
                }, checkIntervalMs);
            }, 600); // Delay allowing network request to be initiated and captured
        });
    }

    // --- YOUR ORIGINAL processAlert, adapted ---
    async function processAlert(row) {
        const now = Date.now();
        if (now - lastFetchTime < FETCH_INTERVAL) {
            setTimeout(() => processAlert(row), FETCH_INTERVAL - (now - lastFetchTime));
            return;
        }
        lastFetchTime = now;

        const rowId = row.getAttribute("row-id");
        if (!rowId) return;

        const alertData = extractAlertData(row);
        if (!alertData) return;

        const alertHash = generateAlertHash(alertData); // Your visual hash
        const lastProcessed = processedAlerts.get(rowId);
        if (lastProcessed && lastProcessed.hash === alertHash && (now - lastProcessed.timestamp) < 5000) {
            return;
        }

        const outcomeCell = row.querySelector('div[col-id="rowOutcome"]');
        if (!outcomeCell) {
            console.error(`[processAlert] Outcome cell not found in row ${rowId}. Cannot simulate click.`);
            // If you want to send data even without sniffed ID (using rowId-derived one):
            // if (alertData.eventIdFromRowAttribute) {
            //     alertData.eventId = alertData.eventIdFromRowAttribute;
            //     console.warn(`[processAlert] Sending with eventId from rowId: ${alertData.eventId}`);
            //     // ... proceed to send ...
            // }
            return;
        }

        console.log(`[processAlert] New distinct alert for row ${rowId}. Simulating click.`);
        const clickTimestamp = Date.now();
        outcomeCell.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
        
        const sniffedEventId = await waitForSniffedEventId(clickTimestamp);
        
        if (sniffedEventId) {
            alertData.eventId = sniffedEventId; // THIS IS THE KEY!
        } else {
            console.error(`[processAlert] CRITICAL: Failed to get a reliable SNIFFED eventId for row ${rowId}. Alert data may be using fallback or be incomplete.`);
            // Fallback to the eventId parsed from rowId, if it exists and you want to risk it
            // For now, we will only proceed if sniffedEventId is good.
            if (alertData.eventIdFromRowAttribute) {
                 console.warn(`[processAlert] Using eventId from row-id as fallback: ${alertData.eventIdFromRowAttribute}`);
                 alertData.eventId = alertData.eventIdFromRowAttribute; // Use with caution
            } else {
                console.error(`[processAlert] No eventId could be determined for row ${rowId}. Cannot forward to Python.`);
                processedAlerts.set(rowId, { hash: alertHash, timestamp: now, eventId: null }); // Mark as processed to avoid loops
                return;
            }
        }
        
        console.log(`[processAlert] Forwarding to Python. EventID: ${alertData.eventId}, Row: ${rowId}, Data:`, alertData);
        chrome.runtime.sendMessage({ type: "forwardToPython", payload: alertData }, response => {
            if (chrome.runtime.lastError) console.error(`[processAlert] Error sending to background for ${rowId}:`, chrome.runtime.lastError.message);
            // else console.log(`[processAlert] Response from background for ${rowId}:`, response);
        });

        processedAlerts.set(rowId, { hash: alertHash, timestamp: now, eventId: alertData.eventId });
    }

    // --- YOUR ORIGINAL processRow ---
    function processRow(row) {
        const rowId = row.getAttribute("row-id");
        if (!rowId) return;
        const alertCell = row.querySelector('div[col-id="alert"]');
        if (!alertCell) return;
        const alertText = alertCell.textContent.toLowerCase();
        if (!alertText.includes("second")) return; // Your filter
        
        // console.log(`[processRow] MATCHED "second" for row ${rowId}.`);
        processAlert(row);
    }

    // --- YOUR ORIGINAL monitorRows ---
    async function monitorRows() {
        const containerSelector = '.ag-center-cols-container'; // YOUR ORIGINAL WORKING SELECTOR
        const container = await waitForElement(containerSelector, 20000); // Wait longer if needed
        
        if (container) {
            console.log(`POD Terminal: Found container ("${containerSelector}"). Initializing.`);
            
            const existingRows = container.querySelectorAll('.ag-row');
            // console.log(`POD Terminal: Processing ${existingRows.length} existing rows.`);
            existingRows.forEach(row => processRow(row));

            const observer = new MutationObserver(mutations => {
                mutations.forEach(mutation => {
                    if (mutation.type === 'childList' && mutation.addedNodes.length > 0) {
                        mutation.addedNodes.forEach(node => {
                            if (node.nodeType === Node.ELEMENT_NODE && node.matches && node.matches('.ag-row')) {
                                // console.log("POD Terminal: New .ag-row by observer:", node.getAttribute("row-id"));
                                processRow(node);
                            }
                        });
                    }
                });
            });
            observer.observe(container, { childList: true, subtree: true }); // Your original observer options
            console.log("POD Terminal: MutationObserver is now active.");
        } else {
            console.error("POD Terminal: CRITICAL - Failed to find container:", containerSelector);
        }
    }
    
    // Remove or comment out the activeEventIds and its setInterval if not used for realtime.html display via content.js
    // const activeEventIds = new Set(); 
    // setInterval(() => { /* your original refresh logic if needed */ }, 10000); 

    setTimeout(monitorRows, 4000); // Your original timeout
    console.log("POD Content Script: Initialization complete, monitorRows scheduled.");
})();