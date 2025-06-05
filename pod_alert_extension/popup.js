let fetchedData = [];

document.getElementById('fetchButton').addEventListener('click', () => {
    document.getElementById('results').innerHTML = 'Fetching event IDs...';
    console.log('Popup: Fetching event IDs...');

    chrome.tabs.query({ active: true, currentWindow: true }, tabs => {
        const activeTab = tabs[0];
        if (!activeTab) {
            document.getElementById('results').innerHTML = 'No active tab found.';
            console.error('Popup: No active tab found.');
            return;
        }

        chrome.tabs.sendMessage(activeTab.id, { action: 'getEventIds' }, response => {
            if (chrome.runtime.lastError) {
                document.getElementById('results').innerHTML = `Error: ${chrome.runtime.lastError.message}`;
                console.error('Popup: Error sending message to content script:', chrome.runtime.lastError.message);
                return;
            }

            if (response.success) {
                const eventIds = response.eventIds;
                console.log('Popup: Extracted event IDs:', eventIds);

                if (eventIds.length === 0) {
                    document.getElementById('results').innerHTML = 'No alerts found.';
                    console.log('Popup: No alerts found.');
                    return;
                }

                document.getElementById('results').innerHTML = 'Fetching odds...';
                console.log('Popup: Fetching odds for event IDs:', eventIds);

                chrome.runtime.sendMessage({ action: 'fetchOdds', eventIds }, response => {
                    const resultsDiv = document.getElementById('results');
                    if (response.success) {
                        console.log('Popup: Successfully fetched odds:', response.data);
                        if (response.data.length === 0) {
                            resultsDiv.innerHTML = 'No data found.';
                            console.log('Popup: No data found from API.');
                            return;
                        }

                        fetchedData = response.data;

                        let html = '<table border="1"><tr><th>Event ID</th><th>Match</th><th>Market</th><th>Outcome</th><th>Current Odds</th><th>Previous Odds</th><th>Opener Odds</th><th>No-Vig Price</th></tr>';
                        response.data.forEach(row => {
                            html += `<tr>
                                <td>${row.eventId}</td>
                                <td>${row.matchDetails}</td>
                                <td>${row.market}</td>
                                <td>${row.outcome}</td>
                                <td>${row.currentOdds}</td>
                                <td>${row.previousOdds}</td>
                                <td>${row.openerOdds}</td>
                                <td>${row.noVigPrice}</td>
                            </tr>`;
                        });
                        html += '</table>';
                        html += '<button id="saveButton">Save to Google Sheets</button>';
                        resultsDiv.innerHTML = html;

                        document.getElementById('saveButton').addEventListener('click', saveToGoogleSheets);
                    } else {
                        resultsDiv.innerHTML = `Error: ${response.error}`;
                        console.error('Popup: Error fetching odds:', response.error);
                    }
                });
            } else {
                document.getElementById('results').innerHTML = `Error fetching event IDs: ${response.error}`;
                console.error('Popup: Error fetching event IDs:', response.error);
            }
        });
    });
});

function saveToGoogleSheets() {
    console.log('Popup: Attempting to save to Google Sheets...');
    chrome.identity.getAuthToken({ interactive: true }, token => {
        if (chrome.runtime.lastError || !token) {
            console.error('Popup: Error authenticating with Google:', chrome.runtime.lastError);
            document.getElementById('results').innerHTML += '<p>Error authenticating with Google.</p>';
            return;
        }

        console.log('Popup: OAuth token obtained:', token);

        const values = fetchedData.map(row => [
            row.eventId,
            row.matchDetails,
            row.market,
            row.outcome,
            row.currentOdds,
            row.previousOdds,
            row.openerOdds,
            row.noVigPrice,
        ]);

        const headers = [
            'Event ID',
            'Match Details',
            'Market',
            'Outcome',
            'Current Odds',
            'Previous Odds',
            'Opener Odds',
            'No-Vig Price',
        ];

        const body = {
            values: [headers, ...values],
        };

        console.log('Popup: Sending data to Google Sheets:', body);

        fetch('https://sheets.googleapis.com/v4/spreadsheets/1lmEPtEeFN8ewQD7fJTJn2T_dr7DwuHgTXNMO_ijIjNg/values/Pinnacle Odds Data!A1:append?valueInputOption=RAW', {
            method: 'POST',
            headers: {
                'Authorization': `Bearer ${token}`,
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(body),
        })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! Status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            console.log('Popup: Google Sheets API success:', data);
            document.getElementById('results').innerHTML += '<p>Data saved to Google Sheets!</p>';
        })
        .catch(error => {
            console.error('Popup: Error saving to Google Sheets:', error);
            document.getElementById('results').innerHTML += `<p>Error saving to Google Sheets: ${error.message}</p>`;
        });
    });
}