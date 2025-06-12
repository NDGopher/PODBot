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
    console.log("Realtime.js v7.9+++ (EV Sort, Status, Clean Names, NVP/BetBCK/Alert Log, Local Time, HRE Hide) Loaded.");

    const MAX_EVENTS_TO_DISPLAY = 5;
    const REFRESH_INTERVAL_MS = 3000;
    const FLASH_DURATION_MS = 1400;
    const POSITIVE_EV_THRESHOLD = 0.0001;
    const AUTO_DISMISS_MINUTES = 3; // 3 minutes
    const BETBCK_REFRESH_INTERVAL_MS = 30000; // 30 seconds
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
    let alertedEvMarkets = new Set(); // Track alerted +EV markets

    let previousDataSnapshot = {};
    let displayedEventIdsOnPage = new Set();
    let previousNVPs = {};
    let betbckRefreshTimeouts = {};
    let autoDismissTimeouts = {};

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

    function timeSince(ts) {
        if (!ts) return '';
        const now = Date.now();
        const diff = Math.floor((now - ts) / 1000);
        if (diff < 5) return 'just now';
        if (diff < 60) return `${diff}s ago`;
        if (diff < 3600) return `${Math.floor(diff/60)}m ago`;
        if (diff < 86400) return `${Math.floor(diff/3600)}h ago`;
        return `${Math.floor(diff/86400)}d ago`;
    }
    
    function formatLocalTime(ts) {
        if (!ts) return '';
        // If ts is in ms, use as is; if in seconds, convert
        if (ts < 1e12) ts = ts * 1000;
        const d = new Date(ts);
        return d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    }

    function formatLocalDateTime(ts) {
        if (!ts) return '';
        if (ts < 1e12) ts = ts * 1000;
        const d = new Date(ts);
        return d.toLocaleString([], { hour: 'numeric', minute: '2-digit', month: '2-digit', day: '2-digit', year: 'numeric' });
    }

    function americanToDecimal(oddsAm) { if (oddsAm===null || oddsAm===undefined || typeof oddsAm === 'string' && (oddsAm.trim()==='N/A'||oddsAm.trim()==='')) return null; const o=parseFloat(oddsAm); if(isNaN(o)) return null; if (o>0) return (o/100)+1; if (o<0) return (100/Math.abs(o))+1; return null; }
    function getPinnacleMarketSnapshotKey(pName, mType, sel, hdpOrPts = '') { return `${pName}-${mType}-${sel}-${String(hdpOrPts||'').replace(/\./g,'p')}`.replace(/\s+/g,'_').toLowerCase(); }

    function formatTimestamp(ts) { if (!ts && ts !== 0) return 'N/A'; try { return new Date(ts).toLocaleString(); } catch (e) { return 'Invalid Date'; } }
    function formatLastUpdate(ts) { if (!ts && ts !== 0) return 'N/A'; try { return new Date(ts * 1000).toLocaleString(); } catch (e) { return 'Invalid Date'; } }

    function parseStartTime(metaInfo) {
        if (!metaInfo) return '';
        // Extract the string after 'Starts:'
        const match = /Starts:\s*([^|]+)/.exec(metaInfo);
        if (match) {
            let raw = match[1].trim();
            // If already 12-hour format (e.g., 6:40 PM), display as-is
            if (/\d{1,2}:\d{2}\s*[APMapm]{2}/.test(raw)) {
                return metaInfo.replace(match[1], raw);
            }
            // If 24-hour format (e.g., 22:40), convert to 12-hour
            if (/\d{2}:\d{2}/.test(raw)) {
                let [h, m] = raw.split(':');
                h = parseInt(h, 10);
                m = parseInt(m, 10);
                const ampm = h >= 12 ? 'PM' : 'AM';
                let hour12 = h % 12;
                if (hour12 === 0) hour12 = 12;
                return metaInfo.replace(match[1], `${hour12}:${m.toString().padStart(2, '0')} ${ampm}`);
            }
            // Otherwise, display as-is
            return metaInfo.replace(match[1], raw);
        }
        return metaInfo;
    }

    function shouldHideEvent(eventEntryFromServer) {
        // Hide if title or teams contain (Hits+Runs+Errors)
        const title = (eventEntryFromServer.title || '').toLowerCase();
        if (title.includes('hits+runs+errors')) return true;
        if ((eventEntryFromServer.markets || []).some(m => (m.selection || '').toLowerCase().includes('hits+runs+errors'))) return true;
        return false;
    }

    function createTableForEvent(eventId, eventEntryFromServer) {
        // Calculate times
        const now = Date.now();
        const alertTs = eventEntryFromServer.alert_arrival_timestamp ? eventEntryFromServer.alert_arrival_timestamp * 1000 : null;
        const oddsUpdateTs = eventEntryFromServer.last_update ? eventEntryFromServer.last_update * 1000 : null;
        // Format event start time (local)
        let startTime = parseStartTime(eventEntryFromServer.meta_info || '');
        let tableHtml = `<header class='event-header'><div class='event-header-info'><h2 class='event-title'>${eventEntryFromServer.title || ''}</h2><p class='event-meta-info'>${startTime}</p><p class='event-last-update' style='font-size:0.95em;color:#9ca3af;'>Odds Updated: <span title='${formatLocalDateTime(oddsUpdateTs)}'>${timeSince(oddsUpdateTs)}</span></p><p class='event-alert-time' style='font-size:0.9em;color:#9ca3af;'>Alert: <span title='${formatLocalDateTime(alertTs)}'>${timeSince(alertTs)}</span></p></div><div class='event-header-actions'><button class='btn-dismiss' title='Dismiss this alert'>&times;</button></div></header>`;
        tableHtml += `<div class='alert-info-banner'><strong class='alert-description'>${eventEntryFromServer.alert_description || ''}</strong> <span class='alert-meta'>${eventEntryFromServer.alert_meta || ''}</span></div>`;
        tableHtml += `<div class='markets-table-container'><table aria-label='Odds Table'><thead><tr><th>Market</th><th>Selection</th><th>Line</th><th class='col-odds'>Pinnacle NVP</th><th class='col-odds'>BetBCK Odds</th><th class='col-ev'>EV %</th></tr></thead><tbody>`;
        if (eventEntryFromServer.markets && Array.isArray(eventEntryFromServer.markets)) {
            // Sort markets by EV descending
            const sortedMarkets = [...eventEntryFromServer.markets].sort((a, b) => {
                const evA = parseFloat(a.ev);
                const evB = parseFloat(b.ev);
                if (isNaN(evA) && isNaN(evB)) return 0;
                if (isNaN(evA)) return 1;
                if (isNaN(evB)) return -1;
                return evB - evA;
            });
            sortedMarkets.forEach(market => {
                // Clean team names for display
                const selection = cleanTeamName(market.selection, eventEntryFromServer.title);
                // Log Pinnacle NVP changes
                const nvpKey = `${eventId}|${market.market}|${selection}|${market.line}`;
                if (previousNVPs[nvpKey] !== undefined && previousNVPs[nvpKey] !== market.pinnacle_nvp) {
                    console.log(`[NVP Change] ${eventEntryFromServer.title} | ${market.market} | ${selection} | ${market.line}: ${previousNVPs[nvpKey]} -> ${market.pinnacle_nvp}`);
                }
                previousNVPs[nvpKey] = market.pinnacle_nvp;
                tableHtml += `<tr><td>${market.market || ''}</td><td>${selection || ''}</td><td>${market.line || ''}</td><td>${market.pinnacle_nvp || ''}</td><td>${market.betbck_odds || ''}</td><td>${market.ev || ''}</td></tr>`;
            });
        } else {
            tableHtml += `<tr><td colspan='6'>No market data available.</td></tr>`;
        }
        tableHtml += `</tbody></table></div>`;
        return tableHtml;
    }

    function setupAutoDismiss(eventId, eventDiv, alertTs) {
        if (autoDismissTimeouts[eventId]) return; // Only set once
        const now = Date.now();
        const msSinceAlert = now - (alertTs || now);
        const msLeft = Math.max(AUTO_DISMISS_MINUTES * 60 * 1000 - msSinceAlert, 0);
        autoDismissTimeouts[eventId] = setTimeout(() => {
            if (eventDiv && eventDiv.parentNode) {
                eventDiv.remove();
                displayedEventIdsOnPage.delete(eventId);
                dismissedEventIds.add(eventId);
                delete autoDismissTimeouts[eventId];
                updateStatusCount();
                console.log(`[Alert Removed] Event ${eventId} auto-dismissed after ${AUTO_DISMISS_MINUTES} minutes.`);
            }
        }, msLeft);
    }

    function setupBetbckRefresh(eventId, eventEntry, eventDiv) {
        if (betbckRefreshTimeouts[eventId]) clearTimeout(betbckRefreshTimeouts[eventId]);
        // Only refresh if there is a positive EV market
        const hasPositiveEV = (eventEntry.markets || []).some(m => parseFloat(m.ev) >= POSITIVE_EV_THRESHOLD);
        if (hasPositiveEV) {
            betbckRefreshTimeouts[eventId] = setTimeout(() => {
                console.log(`[BetBCK Refresh] Triggered for event: ${eventEntry.title}`);
                // Optionally, you could trigger a manual refresh here if needed
            }, BETBCK_REFRESH_INTERVAL_MS);
        }
    }

    function updateStatusCount() {
        // Only count visible (not dismissed) event cards
        const visibleCount = document.querySelectorAll('.event-container').length;
        setStatus('connected', `Connected - ${visibleCount} active event${visibleCount === 1 ? '' : 's'}`);
    }

    async function fetchAndRefreshAllActiveEvents() {
        try {
            const response = await fetch(`/get_active_events_data`);
            if (!response.ok) { setStatus('disconnected', 'Connection error'); if (mainLoadingMessage) mainLoadingMessage.textContent = `Error fetching`; return; }
            const allEventsDataFromServer = await response.json();
            const sortedEventEntries = Object.entries(allEventsDataFromServer)
                .sort(([,a_entry],[,b_entry]) => (b_entry.alert_arrival_timestamp||0) - (a_entry.alert_arrival_timestamp||0))
                .slice(0, MAX_EVENTS_TO_DISPLAY);
            // Remove dismissed events from DOM
            Array.from(oddsDisplayArea.children).forEach(childDiv => {
                const childId = childDiv.id.replace('event-container-','');
                if (dismissedEventIds.has(childId)) { childDiv.remove(); displayedEventIdsOnPage.delete(childId); }
            });
            if(mainLoadingMessage){const noEvents=document.querySelectorAll('.event-container').length===0; mainLoadingMessage.style.display=noEvents?'block':'none'; if(noEvents)mainLoadingMessage.textContent="No active alerts. Waiting...";}
            const divsToRenderInOrder = [];
            for (const [eventId, eventEntry] of sortedEventEntries) {
                if (shouldHideEvent(eventEntry)) continue;
                if (dismissedEventIds.has(eventId)) continue;
                let eventDiv = document.getElementById(`event-container-${eventId}`);
                let needsFullRender = !eventDiv;
                if (!eventDiv) {
                    eventDiv = document.createElement('div'); eventDiv.className = 'event-container'; eventDiv.id = `event-container-${eventId}`;
                }
                eventDiv.innerHTML = createTableForEvent(eventId, eventEntry);
                divsToRenderInOrder.push(eventDiv);
                if (!displayedEventIdsOnPage.has(eventId)) { displayedEventIdsOnPage.add(eventId); }
                // Setup auto-dismiss and BetBCK refresh
                setupAutoDismiss(eventId, eventDiv, eventEntry.alert_arrival_timestamp ? eventEntry.alert_arrival_timestamp * 1000 : null);
                setupBetbckRefresh(eventId, eventEntry, eventDiv);
            }
            // Smart re-ordering: only re-append if order changed or new divs added
            let currentDomOrder = Array.from(oddsDisplayArea.children);
            let domNeedsReorder = divsToRenderInOrder.length !== currentDomOrder.length;
            if (!domNeedsReorder) {
                for(let i=0; i < divsToRenderInOrder.length; i++) { if (!currentDomOrder[i] || currentDomOrder[i].id !== divsToRenderInOrder[i].id) { domNeedsReorder = true; break; } }
            }
            if (domNeedsReorder) {
                oddsDisplayArea.innerHTML = '';
                divsToRenderInOrder.forEach(div => oddsDisplayArea.appendChild(div));
            }
            // Setup dismiss button
            divsToRenderInOrder.forEach(eventDiv => {
                const btn = eventDiv.querySelector('.btn-dismiss');
                if (btn) {
                    btn.onclick = () => {
                        const eventId = eventDiv.id.replace('event-container-','');
                        eventDiv.remove();
                        displayedEventIdsOnPage.delete(eventId);
                        dismissedEventIds.add(eventId);
                        if (autoDismissTimeouts[eventId]) { clearTimeout(autoDismissTimeouts[eventId]); delete autoDismissTimeouts[eventId]; }
                        if (betbckRefreshTimeouts[eventId]) { clearTimeout(betbckRefreshTimeouts[eventId]); delete betbckRefreshTimeouts[eventId]; }
                        updateStatusCount();
                        console.log(`[Alert Removed] Event ${eventId} manually dismissed.`);
                    };
                }
            });
            updateStatusCount();
        } catch (error) { setStatus('disconnected', 'Connection error'); console.error("[Realtime.js] Error refreshing:", error); if(mainLoadingMessage) mainLoadingMessage.textContent = `Error: ${error.message}`; }
    }

    if (mainLoadingMessage) mainLoadingMessage.textContent = "Fetching initial data...";
    fetchAndRefreshAllActiveEvents();
    setInterval(fetchAndRefreshAllActiveEvents, REFRESH_INTERVAL_MS);

    function showPositiveEvPopup(eventData, marketDetails) {
        const { eventId, homeTeam, awayTeam, periodName } = eventData;
        const { selectionName, lineDisplay, marketType, bckDisplay, pinNvpDisplay, evDisplay } = marketDetails;
        const popupKey = `evPopup_${eventId}_${marketType}_${selectionName}_${lineDisplay}`.replace(/[^a-zA-Z0-9]/g, '_');

        if (window.openedEvPopups[popupKey] && !window.openedEvPopups[popupKey].closed) {
            window.openedEvPopups[popupKey].focus();
            return;
        }

        const popup = window.open('', popupKey, `width=500,height=500,scrollbars=yes,resizable=yes`);
        if (!popup) {
            console.warn("Popup blocked by browser.");
            return;
        }
        window.openedEvPopups[popupKey] = popup;

        // --- Flash animation ---
        popup.document.body.style.transition = 'box-shadow 0.4s, background 0.4s';
        popup.document.body.style.boxShadow = '0 0 0 6px #22c55e';
        popup.document.body.style.background = '#283d2f';
        setTimeout(() => {
            popup.document.body.style.boxShadow = '';
            popup.document.body.style.background = '#1f2937';
        }, 700);

        // --- Console log ---
        console.log(`[+EV POPUP] Triggered for: ${homeTeam} vs ${awayTeam} | ${marketType} | ${selectionName} ${lineDisplay} | EV: ${evDisplay}`);

        let lastOdds = { bck: bckDisplay, pin: pinNvpDisplay };

        function updatePopup() {
            fetch(`/get_active_events_data`, { mode: 'cors' })
                .then(response => response.json())
                .then(data => {
                    const event = data[eventId];
                    let market = null;
                    if (event) {
                        market = event.markets.find(m => m.market === marketType && m.selection === selectionName && m.line === lineDisplay);
                    }
                    let oddsWarning = '';
                    let bckOdds = market ? market.betbck_odds : lastOdds.bck;
                    let pinOdds = market ? market.pinnacle_nvp : lastOdds.pin;
                    let evVal = market ? market.ev : evDisplay;
                    // Confirm odds
                    if (market) {
                        if (parseFloat(bckOdds) <= parseFloat(pinOdds)) {
                            oddsWarning = '<div style="color:#ef4444; font-weight:bold;">Warning: BetBCK odds are no longer better than Pinnacle NVP!</div>';
                        }
                        lastOdds = { bck: bckOdds, pin: pinOdds };
                    }
                    popup.document.body.innerHTML = `
                        <style>
                            body { font-family: system-ui, sans-serif; background-color: #1f2937; color: #f9fafb; padding: 20px; }
                            h3 { color: #3b82f6; }
                            p { margin: 8px 0; line-height: 1.5; }
                            strong { color: #9ca3af; }
                            .ev-value { color: #22c55e; font-weight: bold; font-size: 1.2em; }
                            .bet-btn { background: #3b82f6; color: #fff; border: none; border-radius: 6px; padding: 0.5em 1.2em; font-size: 1.1em; cursor: pointer; margin-top: 10px; }
                            .bet-btn:disabled { background: #888; cursor: not-allowed; }
                            .odds-warning { color: #ef4444; font-weight: bold; }
                            .bet-amount-input { width: 80px; font-size: 1.1em; margin-left: 8px; }
                        </style>
                        <h3>Positive EV Opportunity!</h3>
                        <p><strong>Event:</strong> ${homeTeam} vs ${awayTeam}</p>
                        <p><strong>Period:</strong> ${periodName}</p>
                        <hr>
                        <p><strong>Market:</strong> ${marketType}</p>
                        <p><strong>Selection:</strong> ${selectionName} ${lineDisplay}</p>
                        <p><strong>BetBCK Odds:</strong> <span id='bck-odds'>${bckOdds || 'N/A'}</span></p>
                        <p><strong>Pinnacle NVP:</strong> <span id='pin-odds'>${pinOdds || 'N/A'}</span></p>
                        <p class="ev-value">EV: ${evVal || 'N/A'}</p>
                        ${oddsWarning}
                        <div style='margin-top:16px;'>
                            <label for='bet-amount'><strong>Bet Amount:</strong></label>
                            <input id='bet-amount' class='bet-amount-input' type='number' min='1' placeholder='Amount'>
                            <button id='betbck-btn' class='bet-btn'>Bet on BetBCK</button>
                        </div>
                        <div style='margin-top:10px; color:#9ca3af; font-size:0.95em;'>BetBCK integration coming soon: This will inject your bet directly to the BetBCK page.</div>
                    `;
                    // Add button handler
                    popup.document.getElementById('betbck-btn').onclick = function() {
                        const amount = popup.document.getElementById('bet-amount').value;
                        window.open('https://betbck.com/', '_blank');
                        alert('In the future, this will inject your bet directly to BetBCK!\nAmount: ' + amount);
                    };
                })
                .catch(() => popup.close());
        }

        popup.document.title = `+EV Alert: ${selectionName}`;
        updatePopup();
        setInterval(updatePopup, REFRESH_INTERVAL_MS);
    }

    function cleanTeamName(name, eventTitle) {
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