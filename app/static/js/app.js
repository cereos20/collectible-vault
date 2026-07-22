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
    const defaultImg = 'https://images.unsplash.com/photo-1607604276583-eef5d076aa5f?w=600&auto=format&fit=crop&q=80';
    const imgUrl = item.image_url || defaultImg;
    const catClass = `cat-${item.category}`;

    const profitSign = item.profit_loss >= 0 ? '+' : '';
    const isPos = item.profit_loss >= 0;

    // Render metadata tags
    const metaObj = item.metadata_json || {};
    const metaTags = Object.entries(metaObj)
        .slice(0, 3)
        .map(([k, v]) => `<span class="meta-tag">${k.replace('_', ' ')}: ${v}</span>`)
        .join('');

    return `
    <div class="collectible-card glass-panel" id="card-${item.id}">
        <div class="card-image-wrap">
            <img src="${imgUrl}" alt="${escapeHtml(item.title)}" loading="lazy">
            <span class="category-badge ${catClass}">${item.category.replace('_', ' ')}</span>
            ${item.condition_grade ? `<span class="grade-badge">${escapeHtml(item.condition_grade)}</span>` : ''}
        </div>
        <div class="card-title">${escapeHtml(item.title)}</div>
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
            <button class="btn btn-secondary" style="padding:0.4rem 0.6rem; color:var(--accent-rose);" onclick="deleteCollectible(${item.id})">
                <i class="fas fa-trash"></i>
            </button>
        </div>
    </div>`;
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
