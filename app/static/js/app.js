// Universal Collectibles Vault - Client Application Engine
document.addEventListener('DOMContentLoaded', () => {
    initApp();
});

let currentCategory = 'all';
let searchTimeout = null;
let valuationChart = null;

function initApp() {
    fetchDashboardStats();
    loadCollectibles();
    fetchLlmStatus();
    setupEventListeners();
}

function setupEventListeners() {
    // Search input debounce
    const searchInput = document.getElementById('searchInput');
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            clearTimeout(searchTimeout);
            searchTimeout = setTimeout(() => {
                loadCollectibles();
            }, 300);
        });
    }

    // Category pills filter
    const pills = document.querySelectorAll('.filter-pills .pill');
    pills.forEach(pill => {
        pill.addEventListener('click', (e) => {
            pills.forEach(p => p.classList.remove('active'));
            pill.classList.add('active');
            currentCategory = pill.dataset.category || 'all';
            loadCollectibles();
        });
    });

    // Sort Selector
    const sortSelect = document.getElementById('sortSelect');
    if (sortSelect) {
        sortSelect.addEventListener('change', () => loadCollectibles());
    }

    // Refresh Valuations Button
    const refreshBtn = document.getElementById('btnRefreshValuations');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', handleRefreshValuations);
    }

    // Pre-flight confirmation form save
    const preflightForm = document.getElementById('preflightForm');
    if (preflightForm) {
        preflightForm.addEventListener('submit', handlePreflightSubmit);
    }

    // Vision File Input
    const visionFileInput = document.getElementById('visionFileInput');
    if (visionFileInput) {
        visionFileInput.addEventListener('change', handleVisionFileUpload);
    }

    // Manual Barcode Input button
    const btnLookupBarcode = document.getElementById('btnLookupBarcode');
    if (btnLookupBarcode) {
        btnLookupBarcode.addEventListener('click', handleBarcodeLookup);
    }

    // XML Bulk Import File Input
    const xmlFileInput = document.getElementById('xmlFileInput');
    if (xmlFileInput) {
        xmlFileInput.addEventListener('change', handleXmlFileUpload);
    }

    // LLM Dynamic Model Selector
    const llmModelSelect = document.getElementById('llmModelSelect');
    if (llmModelSelect) {
        llmModelSelect.addEventListener('change', handleModelChange);
    }

    // Edit Item Form submit
    const editForm = document.getElementById('editForm');
    if (editForm) {
        editForm.addEventListener('submit', handleEditSubmit);
    }

    // Watchlist Target Form submit
    const watchlistForm = document.getElementById('watchlistForm');
    if (watchlistForm) {
        watchlistForm.addEventListener('submit', handleWatchlistSubmit);
    }
}

// --- FETCH DASHBOARD STATS ---
async function fetchDashboardStats() {
    try {
        const res = await fetch('/api/dashboard/stats');
        if (!res.ok) return;
        const data = await res.json();

        document.getElementById('statTotalItems').innerText = data.total_items;
        document.getElementById('statTotalInvested').innerText = `$${data.total_invested.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
        document.getElementById('statVaultValue').innerText = `$${data.current_vault_value.toLocaleString('en-US', {minimumFractionDigits: 2})}`;
        
        const profitEl = document.getElementById('statProfitLoss');
        const profitSign = data.total_profit_loss >= 0 ? '+' : '';
        profitEl.innerText = `${profitSign}$${data.total_profit_loss.toLocaleString('en-US', {minimumFractionDigits: 2})} (${profitSign}${data.profit_loss_percentage}%)`;
        
        if (data.total_profit_loss >= 0) {
            profitEl.className = 'stat-value positive';
        } else {
            profitEl.className = 'stat-value negative';
        }
    } catch (err) {
        console.error('Failed to load stats:', err);
    }
}

// --- LOAD COLLECTIBLES GRID ---
async function loadCollectibles() {
    const searchVal = document.getElementById('searchInput')?.value || '';
    const sortVal = document.getElementById('sortSelect')?.value || 'newest';
    const grid = document.getElementById('collectiblesGrid');
    
    if (!grid) return;
    grid.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:3rem; color:var(--text-muted);">
        <i class="fas fa-spinner fa-spin fa-2x"></i><br><br>Loading Vault Collectibles...
    </div>`;

    try {
        const url = `/api/items?category=${encodeURIComponent(currentCategory)}&search=${encodeURIComponent(searchVal)}&sort_by=${encodeURIComponent(sortVal)}`;
        const res = await fetch(url);
        const items = await res.json();

        if (items.length === 0) {
            grid.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:4rem; color:var(--text-muted);" class="glass-panel">
                <i class="fas fa-box-open fa-3x" style="margin-bottom:1rem; opacity:0.5;"></i>
                <h3>No Collectibles Found</h3>
                <p>Use "+ Snap & Add Collectible" to add comics, Funko Pops, figures, or cards.</p>
            </div>`;
            return;
        }

        grid.innerHTML = items.map(item => renderCollectibleCard(item)).join('');
    } catch (err) {
        console.error('Error loading items:', err);
        grid.innerHTML = `<div style="grid-column: 1/-1; text-align:center; padding:2rem; color:var(--accent-rose);">
            Failed to connect to API server.
        </div>`;
    }
}

function renderCollectibleCard(item) {
    const defaultImg = '/static/images/placeholder.png';
    const rawUrl = item.image_url || item.cover_url;
    const imgUrl = rawUrl ? rawUrl : defaultImg;
    const catClass = `cat-${item.category}`;

    const profitSign = item.profit_loss >= 0 ? '+' : '';
    const isPos = item.profit_loss >= 0;

    // Render metadata tags
    const metaObj = item.metadata_json || {};
    const metaTags = Object.entries(metaObj)
        .slice(0, 3)
        .map(([k, v]) => `<span class="meta-tag">${k.replace('_', ' ')}: ${v}</span>`)
        .join('');

    const keyBadge = item.is_key_issue
        ? `<span class="badge badge-key" title="${escapeHtml(item.key_reasons || 'Key Issue')}">🔑 KEY ISSUE</span>`
        : '';

    return `
    <div class="collectible-card glass-panel" id="card-${item.id}">
        <div class="card-image-wrap">
            <img src="${imgUrl}" onerror="this.onerror=null; this.src='/static/images/placeholder.png'; this.classList.add('img-fallback');" alt="${escapeHtml(item.title)}" loading="lazy">
            <span class="category-badge ${catClass}">${item.category.replace('_', ' ')}</span>
            ${item.condition_grade ? `<span class="grade-badge">${escapeHtml(item.condition_grade)}</span>` : ''}
        </div>
        <div class="card-title">
            ${escapeHtml(item.title)}
            ${keyBadge}
        </div>
        ${metaTags ? `<div class="meta-pills">${metaTags}</div>` : ''}
        
        <div class="financial-row">
            <div class="price-box">
                <span class="price-label">Market Value</span>
                <span class="price-val">$${item.current_market_value.toLocaleString('en-US', {minimumFractionDigits: 2})}</span>
            </div>
            <div class="gain-badge ${isPos ? 'positive' : 'negative'}">
                <i class="fas fa-arrow-${isPos ? 'up' : 'down'}"></i>
                ${profitSign}${item.profit_loss_percentage}%
            </div>
        </div>

        <div style="display:flex; gap:0.5rem; margin-top:0.5rem;">
            <button class="btn btn-secondary" style="flex:1; padding:0.4rem; font-size:0.8rem;" onclick="openHistoryModal(${item.id})">
                <i class="fas fa-chart-line"></i> Valuation
            </button>
            <button class="btn btn-secondary" style="padding:0.4rem 0.6rem; color:var(--accent-cyan);" onclick="openEditModal(${item.id})">
                <i class="fas fa-edit"></i> Edit
            </button>
            <button class="btn btn-secondary" style="padding:0.4rem 0.6rem; color:var(--accent-rose);" onclick="deleteCollectible(${item.id})">
                <i class="fas fa-trash"></i>
            </button>
        </div>
    </div>`;
}

const renderItemCard = renderCollectibleCard;

function exportVaultCsv() {
    window.location.href = '/api/export/csv';
}

function exportVaultJson() {
    window.location.href = '/api/export/json';
}

let valuationPollInterval = null;

async function triggerAsyncValuation() {
    const btn = document.getElementById('btn-refresh-async') || document.getElementById('btnRefreshValuationsAsync');
    if (btn) btn.disabled = true;

    try {
        const res = await fetch('/api/valuation/refresh-async', { method: 'POST' });
        const data = await res.json();

        const container = document.getElementById('valuationProgressContainer');
        if (container) container.style.display = 'block';

        if (valuationPollInterval) clearInterval(valuationPollInterval);
        valuationPollInterval = setInterval(pollValuationStatus, 1000);
        pollValuationStatus();
    } catch (err) {
        console.error('Failed to trigger async valuation:', err);
        alert('Error triggering background valuation refresh.');
        if (btn) btn.disabled = false;
    }
}

async function pollValuationStatus() {
    try {
        const res = await fetch('/api/valuation/status');
        const data = await res.json();

        const statusMsg = document.getElementById('valuationStatusMsg');
        const progressPct = document.getElementById('valuationProgressPct');
        const progressBar = document.getElementById('valuationProgressBar');
        const container = document.getElementById('valuationProgressContainer');
        const btn = document.getElementById('btn-refresh-async') || document.getElementById('btnRefreshValuationsAsync');

        const pct = data.progress_percentage || 0;
        if (statusMsg) statusMsg.innerText = `Refreshed ${data.processed_items} of ${data.total_items} items (${data.status})`;
        if (progressPct) progressPct.innerText = `${pct}%`;
        if (progressBar) progressBar.style.width = `${pct}%`;

        if (data.status === 'completed' || data.status.startsWith('error') || data.status === 'idle') {
            if (valuationPollInterval) {
                clearInterval(valuationPollInterval);
                valuationPollInterval = null;
            }
            if (btn) btn.disabled = false;
            
            if (data.status === 'completed') {
                setTimeout(() => {
                    if (container) container.style.display = 'none';
                    fetchDashboardStats();
                    loadCollectibles();
                }, 1500);
            }
        }
    } catch (err) {
        console.error('Error polling valuation status:', err);
    }
}

// --- BARCODE SCANNER INTAKE ---
async function handleBarcodeLookup() {
    const input = document.getElementById('barcodeInput');
    const code = input ? input.value.trim() : '';
    if (!code) {
        alert('Please enter a valid UPC barcode number.');
        return;
    }

    try {
        const res = await fetch('/api/intake/barcode', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ barcode: code })
        });
        const data = await res.json();
        
        openPreflightModal({
            title: data.preflight_data.title,
            category: data.preflight_data.category,
            purchase_price: data.preflight_data.purchase_price,
            current_market_value: data.preflight_data.estimated_market_value,
            condition_grade: data.preflight_data.condition_grade,
            barcode: code,
            confidence: 0.95,
            image_url: 'https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?w=600&auto=format&fit=crop&q=80',
            metadata: data.preflight_data.metadata_json
        });
    } catch (err) {
        alert('Error parsing barcode: ' + err.message);
    }
}

// --- VISION AI FILE UPLOAD ---
async function handleVisionFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    // Show scanner laser visualizer
    const scannerOverlay = document.getElementById('scannerOverlay');
    if (scannerOverlay) scannerOverlay.style.display = 'flex';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/intake/vision', {
            method: 'POST',
            body: formData
        });
        const result = await res.json();
        
        if (scannerOverlay) scannerOverlay.style.display = 'none';

        openPreflightModal({
            title: result.title,
            category: result.category,
            purchase_price: roundTwo(result.estimated_market_value * 0.4), // estimate original retail
            current_market_value: result.estimated_market_value,
            condition_grade: result.condition_estimate,
            confidence: result.confidence_score,
            image_url: URL.createObjectURL(file),
            metadata: result.extracted_metadata,
            summary: result.summary
        });
    } catch (err) {
        if (scannerOverlay) scannerOverlay.style.display = 'none';
        alert('Vision LLM Intake failed: ' + err.message);
    }
}

// --- PRE-FLIGHT CONFIRMATION MODAL ---
function openPreflightModal(data) {
    closeModal('intakeModal');
    
    document.getElementById('inputTitle').value = data.title || '';
    document.getElementById('selectCategory').value = data.category || 'other';
    document.getElementById('inputPrice').value = data.purchase_price || 0;
    document.getElementById('inputValue').value = data.current_market_value || 0;
    document.getElementById('inputCondition').value = data.condition_grade || 'Near Mint';
    document.getElementById('inputBarcode').value = data.barcode || '';
    document.getElementById('inputImageUrl').value = data.image_url || '';
    document.getElementById('inputNotes').value = data.summary || '';
    
    document.getElementById('confidenceScore').innerText = `${Math.round((data.confidence || 0.9) * 100)}% Match`;
    
    const previewImg = document.getElementById('preflightImagePreview');
    if (previewImg && data.image_url) {
        previewImg.src = data.image_url;
    }

    openModal('preflightModal');
}

async function handlePreflightSubmit(e) {
    e.preventDefault();
    
    const payload = {
        title: document.getElementById('inputTitle').value.trim(),
        category: document.getElementById('selectCategory').value,
        purchase_price: parseFloat(document.getElementById('inputPrice').value) || 0.0,
        current_market_value: parseFloat(document.getElementById('inputValue').value) || 0.0,
        condition_grade: document.getElementById('inputCondition').value,
        barcode: document.getElementById('inputBarcode').value.trim() || null,
        image_url: document.getElementById('inputImageUrl').value.trim() || null,
        notes: document.getElementById('inputNotes').value.trim() || null,
        metadata_json: {
            added_via: "Mobile Intake Engine",
            timestamp: new Date().toISOString()
        }
    };

    try {
        const res = await fetch('/api/items', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            closeModal('preflightModal');
            fetchDashboardStats();
            loadCollectibles();
        } else {
            alert('Failed to save item to vault.');
        }
    } catch (err) {
        alert('Error saving collectible: ' + err.message);
    }
}

// --- REFRESH VALUATIONS ---
async function handleRefreshValuations() {
    const btn = document.getElementById('btnRefreshValuations');
    const origHtml = btn.innerHTML;
    btn.innerHTML = `<i class="fas fa-sync fa-spin"></i> Refreshing Comps...`;
    btn.disabled = true;

    try {
        const res = await fetch('/api/valuation/refresh', { method: 'POST' });
        const data = await res.json();
        
        btn.innerHTML = `<i class="fas fa-check"></i> Refreshed ${data.items_updated} Items`;
        fetchDashboardStats();
        loadCollectibles();
        
        setTimeout(() => {
            btn.innerHTML = origHtml;
            btn.disabled = false;
        }, 2500);
    } catch (err) {
        btn.innerHTML = origHtml;
        btn.disabled = false;
        alert('Valuation refresh error: ' + err.message);
    }
}

// --- VALUATION HISTORY CHART MODAL ---
async function openHistoryModal(itemId) {
    try {
        const res = await fetch(`/api/items/${itemId}`);
        const item = await res.json();

        document.getElementById('historyModalTitle').innerText = `${item.title} - Valuation History`;
        openModal('historyModal');

        const ctx = document.getElementById('historyChartCanvas').getContext('2d');
        
        if (valuationChart) valuationChart.destroy();

        const labels = item.valuation_history.map(h => new Date(h.recorded_at).toLocaleDateString());
        const dataPoints = item.valuation_history.map(h => h.value);

        valuationChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels.length ? labels : ['Current'],
                datasets: [{
                    label: 'Market Value ($)',
                    data: dataPoints.length ? dataPoints : [item.current_market_value],
                    borderColor: '#8b5cf6',
                    backgroundColor: 'rgba(139, 92, 246, 0.15)',
                    fill: true,
                    tension: 0.3,
                    pointRadius: 5,
                    pointHoverRadius: 8
                }]
            },
            options: {
                responsive: true,
                plugins: {
                    legend: { display: false }
                },
                scales: {
                    x: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af' } },
                    y: { grid: { color: 'rgba(255,255,255,0.05)' }, ticks: { color: '#9ca3af' } }
                }
            }
        });
    } catch (err) {
        alert('Error loading history: ' + err.message);
    }
}

// --- DELETE ITEM ---
async function deleteCollectible(itemId) {
    if (!confirm('Are you sure you want to delete this collectible from your vault?')) return;
    
    try {
        const res = await fetch(`/api/items/${itemId}`, { method: 'DELETE' });
        if (res.ok) {
            fetchDashboardStats();
            loadCollectibles();
        }
    } catch (err) {
        alert('Delete failed: ' + err.message);
    }
}

// --- XML BULK IMPORT UPLOADER ---
async function handleXmlFileUpload(e) {
    const file = e.target.files[0];
    if (!file) return;

    const progressEl = document.getElementById('xmlImportProgress');
    const toastEl = document.getElementById('xmlImportToast');
    const uploadBox = document.getElementById('xmlUploadBox');

    if (progressEl) progressEl.style.display = 'block';
    if (toastEl) toastEl.style.display = 'none';
    if (uploadBox) uploadBox.style.opacity = '0.5';

    const formData = new FormData();
    formData.append('file', file);

    try {
        const res = await fetch('/api/import/xml', {
            method: 'POST',
            body: formData
        });
        const result = await res.json();

        if (progressEl) progressEl.style.display = 'none';
        if (uploadBox) uploadBox.style.opacity = '1';

        if (res.ok && (result.status === 'success' || result.imported_count > 0)) {
            if (toastEl) {
                toastEl.style.display = 'block';
                toastEl.style.backgroundColor = 'rgba(16, 185, 129, 0.2)';
                toastEl.style.border = '1px solid var(--accent-emerald)';
                toastEl.style.color = '#6ee7b7';
                toastEl.innerHTML = `<i class="fas fa-check-circle"></i> Successfully imported <strong>${result.imported_count}</strong> comic(s) into vault!`;
            }

            // Trigger dynamic update of vault dashboard
            loadStats();
            loadItems();
        } else {
            const errorMsg = (result.errors && result.errors.length) ? result.errors.join('<br>') : 'Failed to import XML file.';
            if (toastEl) {
                toastEl.style.display = 'block';
                toastEl.style.backgroundColor = 'rgba(244, 63, 94, 0.2)';
                toastEl.style.border = '1px solid var(--accent-rose)';
                toastEl.style.color = '#fda4af';
                toastEl.innerHTML = `<i class="fas fa-exclamation-triangle"></i> Import Error: ${errorMsg}`;
            }
        }
    } catch (err) {
        if (progressEl) progressEl.style.display = 'none';
        if (uploadBox) uploadBox.style.opacity = '1';
        if (toastEl) {
            toastEl.style.display = 'block';
            toastEl.style.backgroundColor = 'rgba(244, 63, 94, 0.2)';
            toastEl.style.border = '1px solid var(--accent-rose)';
            toastEl.style.color = '#fda4af';
            toastEl.innerHTML = `<i class="fas fa-exclamation-triangle"></i> Upload Failed: ${err.message}`;
        }
    }

    // Reset file input
    e.target.value = '';
}

// Global aliases per requirements (trigger loadStats() and loadItems())
function loadStats() {
    return fetchDashboardStats();
}
function loadItems() {
    return loadCollectibles();
}

window.loadStats = loadStats;
window.loadItems = loadItems;

// --- OLLAMA LLM HEALTH & DYNAMIC MODEL SELECTOR ---
let currentLlmStatusData = null;

async function fetchLlmStatus() {
    try {
        const res = await fetch('/api/llm/status');
        if (!res.ok) return;
        const data = await res.json();
        currentLlmStatusData = data;

        const badge = document.getElementById('llmBadge');
        const textEl = document.getElementById('llmStatusText');
        const selectEl = document.getElementById('llmModelSelect');

        if (data.status === 'online') {
            if (badge) {
                badge.className = 'llm-badge online';
                badge.title = `Connected to Ollama host at ${data.host}`;
            }
            if (textEl) {
                textEl.innerHTML = `<i class="fas fa-circle status-dot"></i> LLM: Connected (${escapeHtml(data.active_model)})`;
            }
        } else {
            if (badge) {
                badge.className = 'llm-badge offline';
                badge.title = data.troubleshooting || 'Ollama offline';
            }
            if (textEl) {
                textEl.innerHTML = `<i class="fas fa-circle status-dot"></i> LLM: Offline (${escapeHtml(data.active_model)})`;
            }
        }

        // Populate model dropdown selector with full tag names
        if (selectEl && data.models && data.models.length > 0) {
            const activeModel = data.active_model || '';
            let matchedActive = data.models.find(m => m === activeModel) ||
                                data.models.find(m => m.startsWith(activeModel + ':')) ||
                                data.models.find(m => m.startsWith(activeModel)) ||
                                data.models[0];

            selectEl.innerHTML = data.models.map(m => {
                const isSel = (m === matchedActive) ? 'selected' : '';
                return `<option value="${escapeHtml(m)}" ${isSel}>${escapeHtml(m)}</option>`;
            }).join('');
        }
    } catch (err) {
        console.error('Error fetching LLM health status:', err);
    }
}

async function handleModelChange(e) {
    const selectedModel = e.target.value;
    if (!selectedModel) return;

    try {
        const res = await fetch('/api/llm/select-model', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ model: selectedModel })
        });
        const data = await res.json();
        if (res.ok && data.status === 'success') {
            fetchLlmStatus();
            alert(`Active LLM model changed to: ${selectedModel}`);
        } else {
            alert('Failed to change active LLM model.');
        }
    } catch (err) {
        alert('Error updating LLM model: ' + err.message);
    }
}

function handleLlmBadgeClick() {
    if (!currentLlmStatusData) return;
    if (currentLlmStatusData.status === 'offline') {
        alert(`Ollama LLM Status: Offline\nHost: ${currentLlmStatusData.host}\n\nTroubleshooting:\n${currentLlmStatusData.troubleshooting || 'Check OLLAMA_HOST IP or OLLAMA_ORIGINS cors settings on Windows VM.'}`);
    } else {
        alert(`Ollama LLM Status: Online 🟢\nHost: ${currentLlmStatusData.host}\nActive Model: ${currentLlmStatusData.active_model}\nAvailable Models: ${currentLlmStatusData.models.join(', ')}`);
    }
}

// Helper Utilities
function openModal(id) {
    document.getElementById(id)?.classList.add('active');
}
function closeModal(id) {
    document.getElementById(id)?.classList.remove('active');
}
function escapeHtml(str) {
    return (str || '').replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
function roundTwo(num) {
    return Math.round(num * 100) / 100;
}

// --- ITEM EDIT FUNCTIONS ---

async function openEditModal(itemId) {
    try {
        const res = await fetch(`/api/items/${itemId}`);
        if (!res.ok) throw new Error('Item not found');
        const item = await res.json();
        const meta = item.metadata_json || {};

        document.getElementById('editItemId').value = item.id;
        document.getElementById('editTitle').value = item.title || '';
        document.getElementById('editIssue').value = meta.issue_number || meta.issue || '';
        document.getElementById('editGrade').value = item.condition_grade || 'Near Mint';
        document.getElementById('editPrice').value = item.purchase_price || 0;
        document.getElementById('editValue').value = item.current_market_value || 0;
        document.getElementById('editLocation').value = meta.location || '';
        document.getElementById('editStatus').value = meta.status || 'In Vault';
        document.getElementById('editNotes').value = item.notes || '';
        const keyToggle = document.getElementById('editKeyIssueToggle');
        if (keyToggle) keyToggle.checked = !!item.is_key_issue;
        const keyReasons = document.getElementById('editKeyReasons');
        if (keyReasons) keyReasons.value = item.key_reasons || '';

        openModal('editModal');
    } catch (err) {
        alert('Error fetching item details for edit: ' + err.message);
    }
}

async function handleEditSubmit(e) {
    e.preventDefault();
    const itemId = document.getElementById('editItemId').value;

    const payload = {
        title: document.getElementById('editTitle').value.trim(),
        issue_number: document.getElementById('editIssue').value.trim(),
        grade: document.getElementById('editGrade').value.trim(),
        cost_basis: parseFloat(document.getElementById('editPrice').value) || 0.0,
        current_market_value: parseFloat(document.getElementById('editValue').value) || 0.0,
        location: document.getElementById('editLocation').value.trim(),
        status: document.getElementById('editStatus').value,
        is_key_issue: document.getElementById('editKeyIssueToggle')?.checked || false,
        key_reasons: document.getElementById('editKeyReasons')?.value.trim() || null,
        notes: document.getElementById('editNotes').value.trim()
    };

    try {
        const res = await fetch(`/api/items/${itemId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            closeModal('editModal');
            fetchDashboardStats();
            loadCollectibles();
        } else {
            alert('Failed to update collectible item.');
        }
    } catch (err) {
        alert('Error saving item changes: ' + err.message);
    }
}

// --- WATCHLIST FUNCTIONS ---

function openWatchlistModal() {
    fetchWatchlist();
    openModal('watchlistModal');
}

async function fetchWatchlist() {
    const container = document.getElementById('watchlistContainer');
    if (!container) return;

    try {
        const res = await fetch('/api/watchlist');
        const items = await res.json();

        if (items.length === 0) {
            container.innerHTML = `<div style="text-align:center; padding:2rem; color:var(--text-muted);">No watchlist target items added yet.</div>`;
            return;
        }

        container.innerHTML = items.map(w => `
            <div style="display:flex; align-items:center; justify-content:space-between; padding:0.75rem 1rem; margin-bottom:0.5rem; background:rgba(255,255,255,0.03); border-radius:var(--radius-sm); border:1px solid var(--border-color);">
                <div>
                    <strong style="color:white;">${escapeHtml(w.title)} ${w.issue ? '#' + escapeHtml(w.issue) : ''}</strong>
                    <span style="font-size:0.8rem; color:var(--text-muted); margin-left:0.5rem;">[Min Grade: ${escapeHtml(w.min_grade || 'Raw')}]</span>
                </div>
                <div style="display:flex; align-items:center; gap:1rem;">
                    <span style="color:var(--accent-amber); font-weight:700;">Target Max: $${w.target_price.toFixed(2)}</span>
                    <button class="btn btn-secondary" style="padding:0.3rem 0.5rem; color:var(--accent-rose);" onclick="deleteWatchlistItem(${w.id})">
                        <i class="fas fa-trash"></i>
                    </button>
                </div>
            </div>
        `).join('');
    } catch (err) {
        container.innerHTML = `<div style="color:var(--accent-rose);">Error loading watchlist items.</div>`;
    }
}

async function handleWatchlistSubmit(e) {
    e.preventDefault();
    const payload = {
        title: document.getElementById('watchTitle').value.trim(),
        issue: document.getElementById('watchIssue').value.trim() || null,
        min_grade: document.getElementById('watchMinGrade').value.trim() || 'Near Mint',
        target_price: parseFloat(document.getElementById('watchTargetPrice').value) || 0.0
    };

    try {
        const res = await fetch('/api/watchlist', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload)
        });
        if (res.ok) {
            document.getElementById('watchlistForm').reset();
            fetchWatchlist();
        }
    } catch (err) {
        alert('Error adding watchlist item: ' + err.message);
    }
}

async function deleteWatchlistItem(id) {
    try {
        const res = await fetch(`/api/watchlist/${id}`, { method: 'DELETE' });
        if (res.ok) {
            fetchWatchlist();
        }
    } catch (err) {
        alert('Delete failed: ' + err.message);
    }
}

// --- AI ASSISTANT SIDEBAR DRAWER ---
function toggleAssistantDrawer() {
    const drawer = document.getElementById('assistantDrawer');
    const overlay = document.getElementById('assistantDrawerOverlay');
    const modelSelect = document.getElementById('llmModelSelect');
    const modelLabel = document.getElementById('assistantActiveModelLabel');

    if (modelLabel && modelSelect) {
        modelLabel.innerText = modelSelect.value ? `Active Model: ${modelSelect.value}` : 'FastMCP / Ollama';
    }

    if (drawer && overlay) {
        drawer.classList.toggle('active');
        overlay.classList.toggle('active');
    }
}

function handleAssistantKeyPress(e) {
    if (e.key === 'Enter') {
        sendAssistantMessage();
    }
}

function sendQuickPrompt(promptText) {
    const input = document.getElementById('assistantInput');
    if (input) input.value = promptText;
    sendAssistantMessage(promptText);
}

async function sendAssistantMessage(promptText) {
    const input = document.getElementById('assistantInput');
    const msg = promptText || (input ? input.value.trim() : '');
    if (!msg) return;

    if (input) input.value = '';

    const chatBox = document.getElementById('assistantChatBox');
    if (!chatBox) return;

    // Append User Bubble
    const userBubble = document.createElement('div');
    userBubble.className = 'chat-bubble user-bubble';
    userBubble.innerText = msg;
    chatBox.appendChild(userBubble);

    // Append Loading Assistant Bubble
    const loadingId = 'loading-' + Date.now();
    const loadingBubble = document.createElement('div');
    loadingBubble.className = 'chat-bubble assistant-bubble';
    loadingBubble.id = loadingId;
    loadingBubble.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Analyzing vault context...`;
    chatBox.appendChild(loadingBubble);
    chatBox.scrollTop = chatBox.scrollHeight;

    const selectedModel = document.getElementById('llmModelSelect')?.value || '';

    try {
        const res = await fetch('/api/assistant/chat', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ prompt: msg, model: selectedModel })
        });
        const data = await res.json();
        
        const loader = document.getElementById(loadingId);
        if (loader) {
            loader.innerText = data.response || 'No response generated.';
        }
    } catch (err) {
        const loader = document.getElementById(loadingId);
        if (loader) {
            loader.innerText = `Error: ${err.message}`;
        }
    }
    chatBox.scrollTop = chatBox.scrollHeight;
}


// --- AI ENDPOINT SETTINGS MODAL ---
async function openAiSettingsModal() {
    const input = document.getElementById('ollamaHostInput');
    const resultBox = document.getElementById('ollamaTestResult');
    if (resultBox) {
        resultBox.style.display = 'none';
        resultBox.innerHTML = '';
    }

    try {
        const res = await fetch('/api/settings/ollama');
        if (res.ok) {
            const data = await res.json();
            if (input && data.ollama_host) {
                input.value = data.ollama_host;
            }
        }
    } catch (err) {
        console.error('Failed to fetch Ollama settings:', err);
    }

    openModal('aiSettingsModal');
}

async function testOllamaHostConnection() {
    const input = document.getElementById('ollamaHostInput');
    const resultBox = document.getElementById('ollamaTestResult');
    const targetHost = input ? input.value.trim() : '';

    if (!targetHost) {
        alert('Please enter an Ollama Host URL to test.');
        return;
    }

    if (resultBox) {
        resultBox.style.display = 'block';
        resultBox.style.background = 'rgba(0,0,0,0.3)';
        resultBox.style.color = '#ffffff';
        resultBox.innerHTML = `<i class="fas fa-spinner fa-spin"></i> Testing connection to <code>${escapeHtml(targetHost)}</code>...`;
    }

    try {
        const res = await fetch('/api/settings/test-host', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ ollama_host: targetHost })
        });
        const data = await res.json();

        if (resultBox) {
            if (data.online) {
                resultBox.style.background = 'rgba(46, 204, 113, 0.15)';
                resultBox.style.borderColor = 'rgba(46, 204, 113, 0.4)';
                resultBox.innerHTML = `
                    <div style="color: #2ecc71; font-weight: 600; font-size: 0.9rem;">
                        <i class="fas fa-check-circle"></i> ${escapeHtml(data.message)}
                    </div>
                    <div style="color: var(--text-muted); margin-top: 0.3rem; font-size: 0.8rem;">
                        Installed Models: ${data.models ? data.models.map(m => escapeHtml(m)).join(', ') : 'None'}
                    </div>`;
            } else {
                resultBox.style.background = 'rgba(231, 76, 60, 0.15)';
                resultBox.style.borderColor = 'rgba(231, 76, 60, 0.4)';
                resultBox.innerHTML = `
                    <div style="color: #e74c3c; font-weight: 600; font-size: 0.9rem;">
                        <i class="fas fa-exclamation-triangle"></i> ${escapeHtml(data.message)}
                    </div>
                    <div style="color: var(--text-muted); margin-top: 0.3rem; font-size: 0.8rem;">
                        Ensure Ollama is running and OLLAMA_ORIGINS is set to allow connections.
                    </div>`;
            }
        }
    } catch (err) {
        if (resultBox) {
            resultBox.style.background = 'rgba(231, 76, 60, 0.15)';
            resultBox.style.borderColor = 'rgba(231, 76, 60, 0.4)';
            resultBox.innerHTML = `<div style="color: #e74c3c; font-weight:600;"><i class="fas fa-exclamation-triangle"></i> Connection Error: ${escapeHtml(err.message)}</div>`;
        }
    }
}

async function saveOllamaHostSetting() {
    const input = document.getElementById('ollamaHostInput');
    const targetHost = input ? input.value.trim() : '';

    if (!targetHost) {
        alert('Ollama Host URL cannot be empty.');
        return;
    }

    try {
        const res = await fetch('/api/settings/ollama', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ ollama_host: targetHost })
        });
        const data = await res.json();

        if (res.ok && data.status === 'success') {
            closeModal('aiSettingsModal');
            // Refresh LLM status and models dropdown immediately
            await fetchLlmStatus();
            alert(`Ollama Host Endpoint saved: ${data.ollama_host}`);
        } else {
            alert(`Failed to save settings: ${data.detail || 'Unknown error'}`);
        }
    } catch (err) {
        alert(`Error saving Ollama Host endpoint: ${err.message}`);
    }
}

