const urlParams = new URLSearchParams(window.location.search);
const eventId = urlParams.get('eventId');
document.title = `Real-Time Odds - ${eventId}`;
console.log("realtime.js loaded with eventId:", eventId);

// Refresh every 5 seconds
setInterval(() => {
    console.log("Requesting updated odds for eventId:", eventId);
    chrome.runtime.sendMessage({ type: "fetchOddsFromOutcome", eventId }, response => {
        if (chrome.runtime.lastError) {
            console.error("Error requesting updated odds:", chrome.runtime.lastError);
        } else {
            console.log("Update odds response:", response);
        }
    });
}, 5000);