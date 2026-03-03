document.addEventListener('DOMContentLoaded', () => {
    let analysisResults = {}; // Removed global window.analysisResults

    const modelSelect = document.getElementById('model');
    const urlInput = document.getElementById('url');
    const startBtn = document.getElementById('start-btn');
    const exportBtn = document.getElementById('export-btn');

    // Screenshot modal logic
    const screenshotModal = document.getElementById('screenshot-modal');
    const screenshotModalImg = document.getElementById('screenshot-modal-img');
    const screenshotModalClose = document.getElementById('screenshot-modal-close');

    document.getElementById('screenshot-img').addEventListener('click', () => {
        screenshotModalImg.src = document.getElementById('screenshot-img').src;
        screenshotModal.style.display = 'flex';
    });

    screenshotModalClose.addEventListener('click', () => {
        screenshotModal.style.display = 'none';
    });

    screenshotModal.addEventListener('click', (e) => {
        if (e.target === screenshotModal) {
            screenshotModal.style.display = 'none';
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (screenshotModal.style.display === 'flex') {
                screenshotModal.style.display = 'none';
            }
            const detailModal = document.getElementById('detail-modal');
            if (detailModal && detailModal.style.display === 'flex') {
                detailModal.style.display = 'none';
            }
        }
    });

    // Detail modal logic
    const detailModal = document.getElementById('detail-modal');
    const detailModalClose = document.getElementById('detail-modal-close');
    const detailModalTitle = document.getElementById('detail-modal-title');
    const detailModalBody = document.getElementById('detail-modal-body');

    detailModalClose.addEventListener('click', () => {
        detailModal.style.display = 'none';
    });

    detailModal.addEventListener('click', (e) => {
        if (e.target === detailModal) {
            detailModal.style.display = 'none';
        }
    });

    function showDetailModal(category, description, fullText) {
        detailModalTitle.textContent = category;

        // Search fullText for a section that matches this category
        const escaped = category.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const pattern = new RegExp('(?:^|\\n)(#{1,4}\\s*.*?' + escaped + '.*?)(?=\\n#{1,4}\\s|$)', 'is');
        const match = fullText.match(pattern);

        let body = '';
        if (match) {
            // Extract from the matched heading to the next heading of same or higher level
            const headingMatch = match[1].match(/^(#{1,4})\s/);
            const level = headingMatch ? headingMatch[1].length : 3;
            const startIdx = fullText.indexOf(match[1]);
            const rest = fullText.substring(startIdx + match[1].length);
            const nextHeading = rest.search(new RegExp('\\n#{1,' + level + '}\\s'));
            const section = nextHeading >= 0
                ? match[1] + rest.substring(0, nextHeading)
                : match[1] + rest;
            body = section.trim();
        } else {
            body = '**' + category + '**\n\n' + description;
        }

        if (window.marked && window.DOMPurify) {
            detailModalBody.innerHTML = DOMPurify.sanitize(marked.parse(body));
        } else {
            detailModalBody.textContent = body;
        }

        detailModal.style.display = 'flex';
    }

    function showError(msg) {
        let errDiv = document.getElementById('error-notification');
        if (!errDiv) {
            errDiv = document.createElement('div');
            errDiv.id = 'error-notification';
            errDiv.className = 'error-notification';
            document.querySelector('.container').insertBefore(errDiv, document.querySelector('.controls'));
        }
        errDiv.textContent = msg;
        errDiv.style.display = 'block';
        setTimeout(() => { errDiv.style.display = 'none'; }, 5000);
    }

    exportBtn.addEventListener('click', () => {
        let out = "AI Web Evaluator Results\n";
        out += "URL: " + urlInput.value + "\n";
        out += "Model: " + modelSelect.value + "\n\n";

        const sections = [
            { id: 'usability', title: 'Usability & Accessibility' },
            { id: 'performance', title: 'Page Performance' },
            { id: 'code', title: 'Code Best Practices' },
            { id: 'security', title: 'Security Issues' }
        ];

        sections.forEach(s => {
            const data = analysisResults[s.id];
            out += `--- ${s.title.toUpperCase()} ---\n`;
            if (data) {
                out += `Score: ${data.score !== null ? data.score + '/10' : 'N/A'}\n\n`;
                out += `Summary:\n${data.summary.trim()}\n\n`;
                out += `Details:\n${data.details.trim()}\n\n`;
            } else {
                out += "No data available.\n\n";
            }
        });

        const blob = new Blob([out], { type: 'text/plain' });
        const objUrl = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = objUrl;
        a.download = 'evaluation_results.txt';
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(objUrl);
    });

    // Fetch and populate available models
    fetch('/api/models')
        .then(res => res.json())
        .then(data => {
            modelSelect.innerHTML = '';
            if (data.models && data.models.length > 0) {
                data.models.forEach(m => {
                    const opt = document.createElement('option');
                    opt.value = m;
                    opt.textContent = m;
                    modelSelect.appendChild(opt);
                });
            } else {
                const opt = document.createElement('option');
                opt.value = "";
                opt.textContent = "No models found";
                modelSelect.appendChild(opt);
                modelSelect.disabled = true;
                startBtn.disabled = true;
                showError("Ensure Ollama is running and has models downloaded.");
            }
        })
        .catch(err => {
            modelSelect.innerHTML = '<option value="">Error loading models</option>';
            console.error('Failed to load models:', err);
        });

    startBtn.addEventListener('click', async () => {
        const url = urlInput.value.trim();
        const model = modelSelect.value;
        if (!url || !model) {
            showError('Please enter a valid URL and select a model.');
            return;
        }

        startBtn.disabled = true;
        exportBtn.disabled = true;
        analysisResults = {};

        const sections = [
            { id: 'usability', prompt: 'usability.txt' },
            { id: 'performance', prompt: 'performance.txt' },
            { id: 'code', prompt: 'code.txt' },
            { id: 'security', prompt: 'security.txt' }
        ];

        // Reset UI
        sections.forEach(s => {
            const h2Span = document.querySelector(`#card-${s.id} .status-indicator`);
            h2Span.className = 'status-indicator loading';
            const content = document.getElementById(`content-${s.id}`);
            content.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">Loading data...</span>';
        });

        document.getElementById('screenshot-container').style.display = 'none';
        document.getElementById('screenshot-img').src = '';
        document.getElementById('scores-container').style.display = 'none';

        startBtn.textContent = 'Fetching Page...';

        try {
            // 1. Fetch HTML content
            const htmlRes = await fetch('/api/fetch', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ url })
            });

            if (!htmlRes.ok) throw new Error('Failed to fetch URL content (possible CORS or network issue)');
            const data = await htmlRes.json();
            if (data.error) throw new Error(data.error);

            const htmlContent = data.html;

            // Show screenshot if available
            if (data.screenshot) {
                const screenshotContainer = document.getElementById('screenshot-container');
                const screenshotImg = document.getElementById('screenshot-img');
                screenshotImg.src = `/static/screenshots/${data.screenshot}`;
                screenshotContainer.style.display = 'block';
            }

            startBtn.textContent = 'Analyzing...';

            // 2. Stream generation for each section asynchronously via server-sent events or stream processing
            await Promise.all(sections.map(s => evaluateSection(s, model, htmlContent)));
            exportBtn.disabled = false;

        } catch (err) {
            sections.forEach(s => {
                const h2Span = document.querySelector(`#card-${s.id} .status-indicator`);
                h2Span.className = 'status-indicator error';
                document.getElementById(`content-${s.id}`).innerHTML = `<span style="color:#f85149">Error: ${err.message}</span>`;
            });
        } finally {
            startBtn.disabled = false;
            startBtn.textContent = 'Start Analysis';
        }
    });

    async function evaluateSection(section, model, html) {
        const contentDiv = document.getElementById(`content-${section.id}`);
        contentDiv.innerHTML = '<div class="eval-content"><span style="color: var(--text-muted); font-style: italic;">Processing...</span></div>';
        const h2Span = document.querySelector(`#card-${section.id} .status-indicator`);

        try {
            const res = await fetch('/api/evaluate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model, prompt_file: section.prompt, html })
            });

            if (!res.ok) throw new Error('Evaluation request failed');

            const reader = res.body.getReader();
            const decoder = new TextDecoder("utf-8");
            let fullText = "";
            let evalContent = contentDiv.querySelector('.eval-content');

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                fullText += chunk;

                // Parse markdown and auto-scroll
                if (window.marked && window.DOMPurify) {
                    evalContent.innerHTML = DOMPurify.sanitize(marked.parse(fullText));
                } else {
                    evalContent.textContent = fullText;
                }
                contentDiv.scrollTop = contentDiv.scrollHeight;
            }

            // Generate Summary Phase
            evalContent.innerHTML = '<span style="color: var(--text-muted); font-style: italic;">Generating table summary...</span>';
            const sumRes = await fetch('/api/summarize', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ model, text: fullText })
            });

            if (!sumRes.ok) throw new Error('Summarization request failed');

            contentDiv.innerHTML = `
                <div class="summary-content"><span style="color: var(--text-muted); font-style: italic;">Structuring table...</span></div>
                <details class="details-section">
                    <summary>View details</summary>
                    <div class="details-content">${window.marked && window.DOMPurify ? DOMPurify.sanitize(marked.parse(fullText)) : fullText}</div>
                </details>
            `;
            const summaryDiv = contentDiv.querySelector('.summary-content');

            const sumReader = sumRes.body.getReader();
            let sumText = "";

            while (true) {
                const { done, value } = await sumReader.read();
                if (done) break;
                const chunk = decoder.decode(value, { stream: true });
                sumText += chunk;

                if (window.marked && window.DOMPurify) {
                    summaryDiv.innerHTML = DOMPurify.sanitize(marked.parse(sumText));
                } else {
                    summaryDiv.textContent = sumText;
                }
                contentDiv.scrollTop = 0;
            }

            // Post-process Score and Rows
            let match = sumText.match(/Score:\s*(\d+)/i);
            let score = null;
            if (match) {
                score = parseInt(match[1]);
                sumText = sumText.replace(match[0], '');
                if (window.marked && window.DOMPurify) {
                    summaryDiv.innerHTML = DOMPurify.sanitize(marked.parse(sumText.trim()));
                } else {
                    summaryDiv.textContent = sumText.trim();
                }
            }

            const rows = Array.from(summaryDiv.querySelectorAll('tr'));
            const severityOrder = { red: 0, yellow: 1, green: 2 };

            // Color rows and sort by severity
            const dataRows = [];
            let headerRow = null;
            rows.forEach(row => {
                const cells = row.querySelectorAll('td');
                if (cells.length > 0) {
                    const text = cells[cells.length - 1].textContent.trim().toLowerCase();
                    if (text === 'red') row.className = 'row-red row-clickable';
                    else if (text === 'yellow') row.className = 'row-yellow row-clickable';
                    else if (text === 'green') row.className = 'row-green row-clickable';
                    else row.className = 'row-clickable';
                    dataRows.push({ row, severity: severityOrder[text] ?? 3 });
                } else {
                    headerRow = row;
                }
            });

            dataRows.sort((a, b) => a.severity - b.severity);

            const tbody = summaryDiv.querySelector('tbody') || summaryDiv.querySelector('table');
            if (tbody) {
                if (headerRow) tbody.appendChild(headerRow);
                dataRows.forEach(({ row }) => tbody.appendChild(row));
            }

            // Add click handlers to open detail modal
            dataRows.forEach(({ row }) => {
                row.addEventListener('click', () => {
                    const cells = row.querySelectorAll('td');
                    if (cells.length < 2) return;
                    const category = cells[0].textContent.trim();
                    const description = cells[1].textContent.trim();
                    showDetailModal(category, description, fullText);
                });
            });

            if (score !== null) {
                let badgeClass = 'score-green';
                if (score < 5) badgeClass = 'score-red';
                else if (score < 8) badgeClass = 'score-yellow';

                const h2 = document.querySelector(`#card-${section.id} h2`);
                let scoreItem = h2.querySelector('.section-score');
                if (!scoreItem) {
                    scoreItem = document.createElement('span');
                    h2.insertBefore(scoreItem, h2.querySelector('.status-indicator'));
                }
                scoreItem.textContent = `${score}/10`;
                scoreItem.className = 'section-score ' + badgeClass;

                document.getElementById('scores-container').style.display = 'flex';
                const globalBadge = document.getElementById(`badge-${section.id}`);
                const globalScoreVal = globalBadge.querySelector('.score-val');
                globalScoreVal.textContent = `${score}/10`;
                globalBadge.className = 'score-badge ' + badgeClass;
            }

            analysisResults[section.id] = {
                score: score,
                summary: sumText,
                details: fullText
            };

            h2Span.className = 'status-indicator done';

        } catch (err) {
            contentDiv.innerHTML = `<span style="color:#f85149">Error: ${err.message}</span>`;
            h2Span.className = 'status-indicator error';
        }
    }
});
