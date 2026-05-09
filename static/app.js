/**
 * API Model Tester - Frontend Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('testForm');
    const testBtn = document.getElementById('testBtn');
    const smartBtn = document.getElementById('smartBtn');
    const syncBtn = document.getElementById('syncBtn');
    const progressDiv = document.getElementById('progress');
    const progressFill = document.getElementById('progressFill');
    const progressText = document.getElementById('progressText');
    const resultsDiv = document.getElementById('results');
    const resultsBody = document.getElementById('resultsBody');
    const summaryDiv = document.getElementById('summary');
    const summaryAvailable = document.getElementById('summaryAvailable');
    const summaryUnavailable = document.getElementById('summaryUnavailable');
    const summaryTotal = document.getElementById('summaryTotal');
    const errorDiv = document.getElementById('error');
    const modelCount = document.getElementById('modelCount');
    const syncStatus = document.getElementById('syncStatus');
    const formatTag = document.getElementById('formatTag');
    const formatType = document.getElementById('formatType');

    let completed = 0;
    let total = 0;
    let availableCount = 0;
    let unavailableCount = 0;
    let isSmartTest = false;

    // Load model count on page load
    loadModelCount();

    // Test form submission (普通测速)
    form.addEventListener('submit', async (e) => {
        e.preventDefault();
        isSmartTest = false;
        await runTest('/api/test/stream', 'Test Models', testBtn);
    });

    // Smart Test button click (智能测速)
    smartBtn.addEventListener('click', async () => {
        const baseUrl = document.getElementById('baseUrl').value.trim();
        const apiKey = document.getElementById('apiKey').value.trim();

        if (!baseUrl || !apiKey) {
            showError('Please enter both API URL and API Key');
            return;
        }

        isSmartTest = true;
        await runTest('/api/test/smart', 'Smart Test', smartBtn);
    });

    async function runTest(endpoint, btnLabel, btn) {
        const baseUrl = document.getElementById('baseUrl').value.trim();
        const apiKey = document.getElementById('apiKey').value.trim();

        // Reset state
        resetState();

        // Show loading state
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner"></span>Testing...';
        progressDiv.classList.remove('hidden');
        resultsDiv.classList.remove('hidden');

        try {
            await startTest(baseUrl, apiKey, endpoint);
        } catch (err) {
            showError('Connection failed: ' + err.message);
            btn.disabled = false;
            btn.innerHTML = btnLabel;
        }
    }

    // Sync button click
    syncBtn.addEventListener('click', async () => {
        syncBtn.disabled = true;
        syncBtn.innerHTML = '<span class="spinner"></span>Syncing...';
        syncStatus.classList.add('hidden');

        try {
            const response = await fetch('/api/models/sync', { method: 'POST' });
            const result = await response.json();

            if (result.success) {
                syncStatus.textContent = `Synced ${result.chat_count} chat models and ${result.image_count} image models from OpenRouter`;
                syncStatus.className = 'sync-status success';
                await loadModelCount();
            } else {
                syncStatus.textContent = 'Sync failed: ' + (result.error || 'Unknown error');
                syncStatus.className = 'sync-status error';
            }
            syncStatus.classList.remove('hidden');
        } catch (err) {
            syncStatus.textContent = 'Sync failed: ' + err.message;
            syncStatus.className = 'sync-status error';
            syncStatus.classList.remove('hidden');
        }

        syncBtn.disabled = false;
        syncBtn.innerHTML = 'Sync from OpenRouter';
    });

    async function loadModelCount() {
        try {
            const response = await fetch('/api/models');
            const data = await response.json();
            const total = data.total || (data.chat_models?.length || 0) + (data.image_models?.length || 0);
            modelCount.textContent = `${total} models loaded`;
        } catch (err) {
            modelCount.textContent = 'Failed to load model count';
        }
    }

    async function startTest(baseUrl, apiKey, endpoint = '/api/test/stream') {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                base_url: baseUrl,
                api_key: apiKey,
            }),
        });

        if (!response.ok) {
            throw new Error('Server error: ' + response.status);
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = '';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split('\n');
            buffer = lines.pop() || '';

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    const data = JSON.parse(line.slice(6));
                    handleEvent(data);
                }
            }
        }

        if (buffer.startsWith('data: ')) {
            const data = JSON.parse(buffer.slice(6));
            handleEvent(data);
        }
    }

    function handleEvent(data) {
        if (data.event === 'start') {
            total = data.total;
            progressText.textContent = `Testing: 0 / ${total}`;
            if (data.phase1 !== undefined) {
                progressText.textContent += ` (平台: ${data.phase1}, 本地: ${data.phase2})`;
            }
            return;
        }

        if (data.event === 'phase') {
            progressText.textContent = `Phase ${data.phase}: ${data.message}`;
            return;
        }

        if (data.event === 'detect') {
            progressText.textContent = data.message;
            // 显示正在检测格式
            if (data.format) {
                formatTag.classList.remove('hidden', 'openai', 'anthropic');
                formatTag.classList.add('detecting');
                formatType.textContent = '正在检测格式...';
            }
            return;
        }

        if (data.event === 'format_detected') {
            progressText.textContent = `格式检测: ${data.message}`;
            // 显示检测到的格式
            formatTag.classList.remove('hidden', 'openai', 'anthropic', 'detecting');
            formatTag.classList.add(data.format);
            formatType.textContent = data.format === 'openai' ? 'OpenAI 格式' : 'Anthropic 格式';
            return;
        }

        if (data.event === 'info') {
            progressText.textContent = data.message;
            return;
        }

        if (data.event === 'complete') {
            finishTest();
            return;
        }

        addResultRow(data);
        completed++;
        updateProgress();
    }

    function addResultRow(result) {
        const row = document.createElement('tr');
        row.id = `row-${result.model}`;

        const modelCell = document.createElement('td');
        modelCell.textContent = result.display_name || result.model;

        const typeCell = document.createElement('td');
        typeCell.innerHTML = `<span class="type-badge">${result.type}</span>`;

        const statusCell = document.createElement('td');
        if (result.available) {
            statusCell.innerHTML = '<span class="status-available">Available</span>';
            availableCount++;
        } else {
            statusCell.innerHTML = `<span class="status-unavailable" title="${result.error || 'Not available'}">Unavailable</span>`;
            unavailableCount++;
        }

        const timeCell = document.createElement('td');
        if (result.available) {
            const timeClass = getTimeClass(result.response_time_ms);
            timeCell.innerHTML = `<span class="${timeClass}">${formatTime(result.response_time_ms)}</span>`;
        } else {
            timeCell.textContent = '-';
        }

        row.appendChild(modelCell);
        row.appendChild(typeCell);
        row.appendChild(statusCell);
        row.appendChild(timeCell);

        resultsBody.appendChild(row);
        updateSummary();
    }

    function updateProgress() {
        const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
        progressFill.style.width = percent + '%';
        progressText.textContent = `Testing: ${completed} / ${total}`;
    }

    function updateSummary() {
        summaryAvailable.textContent = `Available: ${availableCount}`;
        summaryUnavailable.textContent = `Unavailable: ${unavailableCount}`;
        summaryTotal.textContent = `Total: ${completed}`;
        summaryDiv.classList.remove('hidden');
    }

    function finishTest() {
        testBtn.disabled = false;
        testBtn.innerHTML = 'Test Models';
        smartBtn.disabled = false;
        smartBtn.innerHTML = 'Smart Test (平台+本地)';
        progressDiv.classList.add('hidden');
    }

    function resetState() {
        completed = 0;
        total = 0;
        availableCount = 0;
        unavailableCount = 0;
        resultsBody.innerHTML = '';
        progressFill.style.width = '0%';
        errorDiv.classList.add('hidden');
        summaryDiv.classList.add('hidden');
        formatTag.classList.add('hidden');
        formatTag.classList.remove('openai', 'anthropic', 'detecting');
    }

    function showError(message) {
        errorDiv.textContent = message;
        errorDiv.classList.remove('hidden');
    }

    function formatTime(ms) {
        if (ms < 1000) {
            return Math.round(ms) + 'ms';
        }
        return (ms / 1000).toFixed(2) + 's';
    }

    function getTimeClass(ms) {
        if (ms < 1000) return 'time-fast';
        if (ms < 3000) return 'time-medium';
        return 'time-slow';
    }
});
