/**
 * main.js — Café Atlas frontend logic
 * =====================================
 * Handles: loading cafes, filtering, search, add, edit price, delete
 * Depends on auth.js being loaded first (for getToken, authHeaders, isLoggedIn, isAdmin, isConfirmed)
 */

// ── STATE ─────────────────────────────────────────────────────────────────────
let allCafes        = [];   // current page's cafés
let activeFilter    = 'all';
let pendingDeleteId = null;
let pendingEditId   = null;

// Pagination state
let currentPage  = 1;
let totalPages   = 1;
let totalCafes   = 0;
let perPage      = 9;
let currentSearch = '';

const DEFAULT_IMG = 'https://images.unsplash.com/photo-1501339847302-ac426a4a7cbb?w=400';

// Bootstrap modal instances (initialised after DOM loads)
let deleteModal, editModal, bsToast;

// ── INIT ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  deleteModal = new bootstrap.Modal(document.getElementById('deleteModal'));
  editModal   = new bootstrap.Modal(document.getElementById('editModal'));
  bsToast     = new bootstrap.Toast(document.getElementById('liveToast'), { delay: 3500 });

  loadCafes();

  document.getElementById('hero-search').addEventListener('keydown', e => {
    if (e.key === 'Enter') handleSearch();
  });
  document.getElementById('edit-price-input').addEventListener('keydown', e => {
    if (e.key === 'Enter') confirmPriceUpdate();
  });
});

// ── SECTION TOGGLE ────────────────────────────────────────────────────────────
async function showSection(name) {
  // Guard: only logged-in confirmed users can see the add form
  if (name === 'add' && !isLoggedIn()) {
    showToast('Please log in to add a café.', 'bg-warning text-dark');
    window.location.href = '/login';
    return;
  }

  if (name === 'add' && !isConfirmed()) {
    // localStorage might be stale — refresh from server before blocking
    const freshUser = await refreshUserProfile();
    if (!freshUser || !freshUser.is_confirmed) {
      showToast('Please confirm your email before adding a café. Check your inbox.', 'bg-warning text-dark');
      return;
    }
    // If we get here, user IS confirmed on server — localStorage was just stale
  }

  document.getElementById('browse-section').style.display = name === 'browse' ? 'block' : 'none';
  document.getElementById('add-section').style.display    = name === 'add'    ? 'block' : 'none';

  // Show/hide FAB — only visible on browse section
  const fab = document.getElementById('fab-add');
  if (fab) {
    fab.style.display = (name === 'browse' && isLoggedIn() && isConfirmed()) ? 'flex' : 'none';
  }
}

// ── LOAD CAFÉS (paginated) ────────────────────────────────────────────────────
/**
 * GET /cafes?page=X&per_page=9&location=Y
 *
 * Fetches one page of cafés at a time from Flask.
 * Flask returns: { cafes, total, page, per_page, total_pages, has_next, has_prev }
 *
 * Why pagination matters:
 *   Without it, 500 cafés = 500 card renders + 500 image loads at once.
 *   With it, only 9 render per request — much faster and lighter.
 */
async function loadCafes(page = 1, search = '') {
  currentPage   = page;
  currentSearch = search;

  try {
    let url = `/cafes?page=${page}&per_page=${perPage}`;
    if (search) url += `&location=${encodeURIComponent(search)}`;

    const res  = await fetch(url);
    if (!res.ok) throw new Error(`Server error: ${res.status}`);
    const data = await res.json();

    allCafes   = data.cafes   || [];
    totalPages  = data.total_pages || 1;
    totalCafes  = data.total      || 0;
    currentPage = data.page       || 1;

    updateStats(data);
    renderGrid(allCafes);
    renderPagination(data);
    updateAddCafeUI();

  } catch (err) {
    console.error('Load error:', err);
    document.getElementById('cafe-grid').innerHTML = `
      <div class="col-12">
        <div class="alert alert-warning">
          <i class="bi bi-exclamation-triangle me-2"></i>
          Could not load cafés. Please check your connection and try again.
        </div>
      </div>`;
    document.getElementById('count-badge').textContent = 'Error';
  }
}

// ── PAGINATION RENDERER ────────────────────────────────────────────────────────
function renderPagination(data) {
  // Remove old pagination if it exists
  const old = document.getElementById('pagination-wrap');
  if (old) old.remove();

  if (data.total_pages <= 1) return;  // no need for pagination

  const wrap = document.createElement('div');
  wrap.id        = 'pagination-wrap';
  wrap.className = 'd-flex justify-content-center align-items-center gap-2 mt-5 flex-wrap';

  // Previous button
  wrap.innerHTML += `
    <button class="page-btn ${!data.has_prev ? 'disabled' : ''}"
            onclick="${data.has_prev ? `goToPage(${data.page - 1})` : ''}"
            ${!data.has_prev ? 'disabled' : ''}>
      <i class="bi bi-chevron-left"></i> Prev
    </button>`;

  // Page number buttons — show window of 5 pages around current
  const start = Math.max(1, data.page - 2);
  const end   = Math.min(data.total_pages, data.page + 2);

  if (start > 1) {
    wrap.innerHTML += `<button class="page-btn" onclick="goToPage(1)">1</button>`;
    if (start > 2) wrap.innerHTML += `<span class="page-ellipsis">…</span>`;
  }

  for (let p = start; p <= end; p++) {
    wrap.innerHTML += `
      <button class="page-btn ${p === data.page ? 'active' : ''}"
              onclick="goToPage(${p})">${p}</button>`;
  }

  if (end < data.total_pages) {
    if (end < data.total_pages - 1) wrap.innerHTML += `<span class="page-ellipsis">…</span>`;
    wrap.innerHTML += `<button class="page-btn" onclick="goToPage(${data.total_pages})">${data.total_pages}</button>`;
  }

  // Next button
  wrap.innerHTML += `
    <button class="page-btn ${!data.has_next ? 'disabled' : ''}"
            onclick="${data.has_next ? `goToPage(${data.page + 1})` : ''}"
            ${!data.has_next ? 'disabled' : ''}>
      Next <i class="bi bi-chevron-right"></i>
    </button>`;

  // Page info text
  const info = document.createElement('div');
  info.className   = 'w-100 text-center mt-2';
  info.style.color = 'var(--muted-txt)';
  info.style.fontSize = '.82rem';
  const from = (data.page - 1) * data.per_page + 1;
  const to   = Math.min(data.page * data.per_page, data.total);
  info.textContent = `Showing ${from}–${to} of ${data.total} cafés`;

  wrap.appendChild(info);

  // Insert after the grid
  const grid = document.getElementById('cafe-grid');
  grid.parentNode.insertBefore(wrap, grid.nextSibling);
}

function goToPage(page) {
  window.scrollTo({ top: 0, behavior: 'smooth' });
  loadCafes(page, currentSearch);
}

// ── ADD CAFÉ UI ───────────────────────────────────────────────────────────────
/**
 * Controls three UI elements based on the user's auth state:
 *
 * 1. FAB (floating button, bottom-right) — shown to confirmed logged-in users
 * 2. Navbar "Add Café" button            — rendered by auth.js renderNavbar()
 * 3. Login prompt card                   — shown to guests at bottom of page
 *
 * Called after cafes load and after auth state changes.
 */
function updateAddCafeUI() {
  const fab         = document.getElementById('fab-add');
  const loginPrompt = document.getElementById('login-prompt');

  if (!fab || !loginPrompt) return;

  if (isLoggedIn() && isConfirmed()) {
    // Confirmed user — show FAB, hide login prompt
    fab.style.display         = 'flex';
    loginPrompt.style.display = 'none';
  } else if (isLoggedIn() && !isConfirmed()) {
    // Logged in but unconfirmed — hide both (confirm banner already shows)
    fab.style.display         = 'none';
    loginPrompt.style.display = 'none';
  } else {
    // Guest — hide FAB, show login prompt
    fab.style.display         = 'none';
    loginPrompt.style.display = 'block';
  }
}

// ── STATS ─────────────────────────────────────────────────────────────────────
// Uses the API total (all cafés) not just the current page count
function updateStats(data) {
  if (data && data.total !== undefined) {
    document.getElementById('stat-total').textContent   = data.total;
    // For wifi/sockets we still use current page — full count needs a separate API call
    // which is overkill for a stats bar. Current page gives a good approximation.
  } else {
    document.getElementById('stat-total').textContent = allCafes.length;
  }
  document.getElementById('stat-wifi').textContent    = allCafes.filter(c => c.has_wifi).length;
  document.getElementById('stat-sockets').textContent = allCafes.filter(c => c.has_sockets).length;
}

// ── FILTER CHIPS ──────────────────────────────────────────────────────────────
function setFilter(filter, el) {
  activeFilter = filter;
  document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('on'));
  el.classList.add('on');
  applyFilter();
}

function applyFilter() {
  // Client-side filter on the current page's cafés (fast, no network request)
  // For a full server-side filter, we'd need to add filter params to the API
  const map = {
    all:     () => [...allCafes],
    wifi:    () => allCafes.filter(c => c.has_wifi),
    sockets: () => allCafes.filter(c => c.has_sockets),
    toilet:  () => allCafes.filter(c => c.has_toilet),
    calls:   () => allCafes.filter(c => c.can_take_calls),
  };
  let filtered = (map[activeFilter] || map.all)();

  const sort = document.getElementById('sort-select')?.value || 'default';

  function parsePrice(p) {
    if (!p || p === 'N/A') return 0;
    return parseFloat(p.replace(/[^0-9.]/g, '')) || 0;
  }
  const sorters = {
    'name-asc':   (a, b) => a.name.localeCompare(b.name),
    'name-desc':  (a, b) => b.name.localeCompare(a.name),
    'price-asc':  (a, b) => parsePrice(a.coffee_price) - parsePrice(b.coffee_price),
    'price-desc': (a, b) => parsePrice(b.coffee_price) - parsePrice(a.coffee_price),
  };
  if (sorters[sort]) filtered.sort(sorters[sort]);

  renderGrid(filtered);
}

// ── SEARCH ────────────────────────────────────────────────────────────────────
// With pagination, search must go back to the server (page 1 of filtered results)
// We can no longer just filter allCafes locally since allCafes is only one page
function handleSearch() {
  const q = document.getElementById('hero-search').value.trim();
  showSection('browse');
  loadCafes(1, q);  // reset to page 1 with the search term
}

// ── RENDER CARDS ──────────────────────────────────────────────────────────────
/**
 * Builds the card HTML for each café.
 *
 * Auth-aware rendering:
 *  - Edit (pencil) button: visible to logged-in confirmed users only
 *  - Delete (trash) button: visible to admins only
 *  - Buttons are hidden (not just disabled) to keep the UI clean
 */
function renderGrid(cafes) {
  const grid = document.getElementById('cafe-grid');
  const from = (currentPage - 1) * perPage + 1;
  const to   = Math.min(currentPage * perPage, totalCafes);
  document.getElementById('count-badge').textContent =
    totalCafes > perPage
      ? `${from}–${to} of ${totalCafes}`
      : `${cafes.length} café${cafes.length !== 1 ? 's' : ''}`;

  if (!cafes.length) {
    grid.innerHTML = `
      <div class="col-12">
        <div class="no-results">
          <div class="no-results-icon">☕</div>
          <h4 class="mb-2">No cafés match your filter</h4>
          <p class="mb-3">Try a different filter, clear your search, or add the first one.</p>
          <button class="btn-prompt-login" onclick="setFilter('all',document.querySelector('.filter-chip'));document.getElementById('hero-search').value=''">
            <i class="bi bi-arrow-counterclockwise me-1"></i>Clear filters
          </button>
        </div>
      </div>`;
    return;
  }

  const loggedIn  = isLoggedIn();
  const confirmed = isConfirmed();
  const admin     = isAdmin();

  grid.innerHTML = cafes.map((c, i) => `
    <div class="col-sm-6 col-lg-4" style="animation-delay:${i * .055}s">
      <div class="cafe-card card h-100">

        <div class="card-img-wrap">
          <img src="${c.img_url || DEFAULT_IMG}" alt="${c.name}" loading="lazy"
               onerror="this.src='${DEFAULT_IMG}'"/>
          ${c.coffee_price ? `<span class="price-badge">${c.coffee_price}</span>` : ''}
        </div>

        <div class="card-body d-flex flex-column">
          <h5 class="card-title-text">${c.name}</h5>
          <p class="card-location mb-1">
            <i class="bi bi-geo-alt me-1"></i>${c.location}
            ${c.seats ? `&nbsp;·&nbsp;<i class="bi bi-people me-1"></i>${c.seats} seats` : ''}
          </p>
          <p class="mb-2" style="font-size:.76rem;color:var(--muted-txt)">
            <i class="bi bi-person-circle me-1"></i>
            ${c.added_by_name
              ? `Added by <strong>${c.added_by_name}</strong>`
              : c.added_by
                ? `Added by user #${c.added_by}`
                : '<em>Original data</em>'
            }
          </p>

          <div class="d-flex flex-wrap gap-1 mb-3">
            ${pill('bi-wifi',      'Wi‑Fi',   c.has_wifi)}
            ${pill('bi-plug',      'Sockets', c.has_sockets)}
            ${pill('bi-door-open', 'Toilet',  c.has_toilet)}
            ${pill('bi-telephone', 'Calls',   c.can_take_calls)}
          </div>

          <div class="d-flex gap-2 mt-auto pt-2 border-top" style="border-color:#e0d8cd!important">
            <a href="${c.map_url}" target="_blank" rel="noopener" class="flex-grow-1">
              <button class="btn-map"><i class="bi bi-map me-1"></i>Map</button>
            </a>

            ${loggedIn && confirmed ? `
              <button class="btn-edit"
                      onclick="openEditModal(${c.id}, '${escQ(c.name)}', '${escQ(c.coffee_price || '')}')"
                      title="Update price">
                <i class="bi bi-pencil"></i>
              </button>` : ''}

            ${admin ? `
              <button class="btn-del" onclick="openDeleteModal(${c.id})" title="Delete café">
                <i class="bi bi-trash3"></i>
              </button>` : ''}
          </div>
        </div>

      </div>
    </div>
  `).join('');
}

// ── HELPERS ───────────────────────────────────────────────────────────────────
function pill(icon, label, ok) {
  return `<span class="amenity ${ok ? 'yes' : 'no'}">
    <i class="bi ${icon}"></i> ${label}
  </span>`;
}

function escQ(str) {
  return String(str || '').replace(/'/g, "\\'").replace(/"/g, '&quot;');
}

// ── ADD CAFÉ ──────────────────────────────────────────────────────────────────
/**
 * POST /cafes
 *
 * Protected route — requires:
 *   1. JWT token in Authorization header  (@jwt_required)
 *   2. Email confirmed                    (@confirmed_required)
 *
 * The token comes from localStorage via authHeaders() in auth.js.
 * Flask checks it, gets the user ID from it, records who added the café.
 */
async function submitNewCafe() {
  const name     = document.getElementById('f-name').value.trim();
  const location = document.getElementById('f-location').value.trim();
  const map_url  = document.getElementById('f-map').value.trim();

  if (!name || !location || !map_url) {
    showToast('Please fill in Name, Location and Map URL.', 'bg-danger');
    return;
  }

  const payload = {
    name,
    location,
    map_url,
    img_url:        document.getElementById('f-img').value.trim()   || DEFAULT_IMG,
    coffee_price:   document.getElementById('f-price').value.trim() || 'N/A',
    seats:          document.getElementById('f-seats').value.trim() || 'Unknown',
    has_wifi:       document.getElementById('f-wifi').checked,
    has_sockets:    document.getElementById('f-sockets').checked,
    has_toilet:     document.getElementById('f-toilet').checked,
    can_take_calls: document.getElementById('f-calls').checked,
  };

  try {
    const res  = await fetch('/cafes', {
      method:  'POST',
      headers: authHeaders(),       // ← sends Authorization: Bearer <token>
      body:    JSON.stringify(payload),
    });
    const data = await res.json();

    if (res.status === 401) {
      showToast('Session expired. Please log in again.', 'bg-danger');
      window.location.href = '/login';
      return;
    }
    if (res.status === 403) {
      // Could be unconfirmed email OR stale localStorage
      // Re-fetch the user profile to get the latest is_confirmed value
      try {
        const meRes  = await fetch('/auth/me', { headers: authHeaders() });
        const meData = await meRes.json();
        if (meRes.ok && meData.user) {
          // Update localStorage with fresh data from server
          const updatedUser = meData.user;
          localStorage.setItem('user', JSON.stringify(updatedUser));
          if (updatedUser.is_confirmed) {
            // Was confirmed on server but localStorage was stale — retry
            showToast('Session refreshed. Trying again…', 'bg-info text-dark');
            await submitNewCafe();
            return;
          }
        }
      } catch (e) { /* ignore refresh error */ }
      showToast('❌ Please confirm your email before adding a café. Check your inbox.', 'bg-warning text-dark');
      return;
    }
    if (!res.ok) {
      showToast(`❌ ${data.error}`, 'bg-danger');
      return;
    }

    // Add to local array with real DB id from the response
    allCafes.push(data.cafe);
    updateStats();
    showSection('browse');
    applyFilter();
    showToast(`✅ "${name}" saved to database!`, 'bg-success');
    clearForm();

  } catch (err) {
    showToast('❌ Could not reach the server.', 'bg-danger');
    console.error(err);
  }
}

function clearForm() {
  ['f-name','f-location','f-price','f-seats','f-map','f-img']
    .forEach(id => document.getElementById(id).value = '');
  ['f-sockets','f-toilet','f-calls']
    .forEach(id => document.getElementById(id).checked = false);
  document.getElementById('f-wifi').checked = true;
}

// ── DELETE CAFÉ ───────────────────────────────────────────────────────────────
/**
 * DELETE /cafes/<id>
 *
 * Admin only — Flask checks:
 *   1. @jwt_required()   → valid token
 *   2. @admin_required   → user.role == 'admin'
 *
 * The edit and delete buttons are only rendered for the right users
 * (see renderGrid above), but Flask enforces it server-side too.
 * Never rely on hiding UI elements alone for security.
 */
function openDeleteModal(id) {
  pendingDeleteId = id;
  deleteModal.show();
}

async function confirmDelete() {
  if (!pendingDeleteId) return;
  const id   = pendingDeleteId;
  const cafe = allCafes.find(c => c.id === id);
  deleteModal.hide();

  try {
    const res  = await fetch(`/cafes/${id}`, {
      method:  'DELETE',
      headers: authHeaders(),
    });
    const data = await res.json();

    if (!res.ok) {
      showToast(`❌ ${data.error}`, 'bg-danger');
      return;
    }

    // Remove from local array — no need to reload all data
    allCafes = allCafes.filter(c => c.id !== id);
    updateStats();
    applyFilter();
    showToast(`🗑 "${cafe?.name}" deleted from database.`, 'bg-secondary');

  } catch (err) {
    showToast('❌ Could not reach the server.', 'bg-danger');
    console.error(err);
  }

  pendingDeleteId = null;
}

// ── UPDATE PRICE ──────────────────────────────────────────────────────────────
/**
 * PATCH /cafes/<id>/price
 *
 * Requires login + confirmed email.
 * Sends only the coffee_price field — Flask updates just that column.
 */
function openEditModal(id, name, currentPrice) {
  pendingEditId = id;
  document.getElementById('edit-cafe-name').textContent = name;
  document.getElementById('edit-price-input').value     = currentPrice;
  editModal.show();
  setTimeout(() => document.getElementById('edit-price-input').focus(), 400);
}

async function confirmPriceUpdate() {
  if (!pendingEditId) return;
  const newPrice = document.getElementById('edit-price-input').value.trim();
  if (!newPrice) { showToast('Please enter a price.', 'bg-warning text-dark'); return; }

  editModal.hide();

  try {
    const res  = await fetch(`/cafes/${pendingEditId}/price`, {
      method:  'PATCH',
      headers: authHeaders(),
      body:    JSON.stringify({ coffee_price: newPrice }),
    });
    const data = await res.json();

    if (!res.ok) {
      showToast(`❌ ${data.error}`, 'bg-danger');
      return;
    }

    // Update the local array with Flask's returned café object
    const idx = allCafes.findIndex(c => c.id === pendingEditId);
    if (idx !== -1) allCafes[idx] = data.cafe;

    applyFilter();
    showToast(`✅ Price updated to ${newPrice}`, 'bg-success');

  } catch (err) {
    showToast('❌ Could not reach the server.', 'bg-danger');
    console.error(err);
  }

  pendingEditId = null;
}

// ── TOAST ─────────────────────────────────────────────────────────────────────
function showToast(msg, cls = 'bg-dark') {
  const el = document.getElementById('liveToast');
  el.className = `toast align-items-center border-0 text-white ${cls}`;
  document.getElementById('toast-msg').textContent = msg;
  bsToast.show();
}
