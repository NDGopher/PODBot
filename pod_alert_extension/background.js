// pod_alert_extension/background.js
console.log("Background Service Worker v4 (Reliable Sniffing) Loaded.");

let lastSniffedSwordfishEvent = {
    eventId: null,
    timestamp: 0,
    url: null // Store the URL for debugging
};

// Listener for the API call POD makes when an event's details are loaded (after a click)
chrome.webRequest.onCompleted.addListener(
  (details) => {
    if (details.url.includes("swordfish-production.up.railway.app/events/")) {
      const match = details.url.match(/events\/(\d+)/); // Extracts digits after /events/
      if (match && match[1]) {
        const capturedEventId = match[1];
        const capturedTimestamp = details.timeStamp; // Timestamp of the request completion

        // Update if it's a different event or a newer timestamp for the same event
        // This helps ensure we have the eventId related to the most recent relevant interaction
        if (capturedEventId !== lastSniffedSwordfishEvent.eventId || capturedTimestamp > lastSniffedSwordfishEvent.timestamp) {
            lastSniffedSwordfishEvent.eventId = capturedEventId;
            lastSniffedSwordfishEvent.timestamp = capturedTimestamp;
            lastSniffedSwordfishEvent.url = details.url; // For logging
            console.log(
              `[BG_WebRequest] CAPTURED/UPDATED Swordfish eventId: ${lastSniffedSwordfishEvent.eventId} from URL: ${details.url} at ${new Date(lastSniffedSwordfishEvent.timestamp).toISOString()}`
            );
        }
      }
    }
  },
  { urls: ["https://swordfish-production.up.railway.app/events/*"] }
);

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
    console.log("[Background] Message received:", message.type);

    if (message.type === "getLatestSniffedEventDetails") { // Renamed for clarity
        console.log(`[Background] Responding to 'getLatestSniffedEventDetails'. Current: ID=${lastSniffedSwordfishEvent.eventId}, TS=${lastSniffedSwordfishEvent.timestamp}, URL=${lastSniffedSwordfishEvent.url}`);
        sendResponse({ 
            eventId: lastSniffedSwordfishEvent.eventId, 
            timestamp: lastSniffedSwordfishEvent.timestamp,
            url: lastSniffedSwordfishEvent.url 
        });
        // Do NOT reset lastSniffedSwordfishEvent here. Content.js needs to compare the timestamp.
        return false; // Indicate synchronous response

    } else if (message.type === "forwardToPython") {
        const pythonServerUrl = "http://localhost:5001/pod_alert";
        const payload = message.payload;

        if (!payload || !payload.eventId) { // Crucially check for eventId in payload
            console.error("[Background] 'forwardToPython' called BUT payload is missing 'eventId'. Payload:", payload);
            sendResponse({ status: "error", reason: "Missing eventId in payload for forwardToPython" });
            return true; // Async but error
        }
        
        console.log(`[Background] Forwarding to Python for eventId: ${payload.eventId}. Payload snippet:`, {home: payload.homeTeam, away: payload.awayTeam, market: payload.betDescription});
        
        fetch(pythonServerUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(response => {
            const contentType = response.headers.get("content-type");
            if (!response.ok) {
                let errorPromise;
                if (contentType && contentType.includes("application/json")) {
                    errorPromise = response.json().then(errData => { throw new Error(`HTTP ${response.status}: ${errData.message || errData.error || response.statusText}`); });
                } else { errorPromise = response.text().then(text => { throw new Error(`HTTP ${response.status}: ${response.statusText}. Server: ${text.substring(0,200)}`); }); }
                return errorPromise;
            }
            if (contentType && contentType.includes("application/json")) { return response.json(); }
            return response.text().then(text => ({ status: "warning", message: "Python response not JSON", raw: text}));
        })
        .then(data => {
            console.log("[Background] Python server response:", data);
            sendResponse({ status: data.status || "success", pythonResponse: data });
        })
        .catch(error => {
            console.error("[Background] Error POSTing to Python server:", error.message);
            sendResponse({ status: "error", reason: `Python POST failed: ${error.message}` });
        });
        return true; // Async
    }
    return true; // Keep channel open for other potential async handlers if any are added
});