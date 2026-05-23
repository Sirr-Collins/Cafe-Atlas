/**
 * auth.js — Shared authentication utilities
 * ==========================================
 * Handles: token storage, navbar rendering, logout, auth headers
 * Loaded on every page via <script src="/static/js/auth.js">
 */

// ── TOKEN HELPERS ────────────────────────────────────────────────────────────

/**
 * Retrieve the JWT token from localStorage.
 * Returns null if not logged in.
 */
function getToken() {
  return localStorage.getItem('token');
}

/**
 * Retrieve the stored user object.
 * Returns null if not logged in.
 */
function getUser() {
  try {
    return JSON.parse(localStorage.getItem('user'));
  } catch {
    return null;
  }
}

/**
 * Build the Authorization header object needed for protected API calls.
 * Every fetch() to a protected route must include this.
 *
 * Usage:
 *   fetch('/cafes', { method:'POST', headers: authHeaders(), body: ... })
 */
function authHeaders() {
  return {
    'Content-Type':  'application/json',
    'Authorization': `Bearer ${getToken()}`,
  };
}

/**
 * Returns true if the user is logged in (token exists in localStorage).
 * NOTE: This only checks local storage — the token might be expired.
 * Flask will reject expired tokens with a 401 on any actual API call.
 */
function isLoggedIn() {
  return !!getToken();
}

/**
 * Returns true if the logged-in user has the 'admin' role.
 */
function isAdmin() {
  const user = getUser();
  return user && user.role === 'admin';
}

/**
 * Returns true if the user has confirmed their email.
 * Reads from localStorage — may be stale if user confirmed after logging in.
 * Call refreshUserProfile() to sync with the server if needed.
 */
function isConfirmed() {
  const user = getUser();
  return user && user.is_confirmed;
}

/**
 * Refreshes the user profile from the server and updates localStorage.
 * Call this when you suspect localStorage is stale (e.g. after email confirmation).
 * Returns the fresh user object, or null on failure.
 */
async function refreshUserProfile() {
  const token = getToken();
  if (!token) return null;
  try {
    const res  = await fetch('/auth/me', {
      headers: { 'Authorization': `Bearer ${token}` }
    });
    if (!res.ok) return null;
    const data = await res.json();
    if (data.user) {
      localStorage.setItem('user', JSON.stringify(data.user));
      return data.user;
    }
  } catch (e) {
    console.warn('Could not refresh user profile:', e);
  }
  return null;
}

// ── LOGOUT ────────────────────────────────────────────────────────────────────

/**
 * Log out the current user.
 *
 * Flow:
 *  1. Call DELETE /auth/logout — Flask adds the JWT to the blocklist DB
 *  2. Clear localStorage (remove token and user data)
 *  3. Redirect to login page
 *
 * Even if the server call fails (network error), we clear localStorage
 * so the user appears logged out on the frontend.
 */
async function logout() {
  try {
    await fetch('/auth/logout', {
      method:  'DELETE',
      headers: authHeaders(),
    });
  } catch (e) {
    console.warn('Logout request failed — clearing local session anyway.');
  } finally {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    window.location.href = '/login';
  }
}

// ── RESEND CONFIRMATION ───────────────────────────────────────────────────────

async function resendConfirmation() {
  const user = getUser();
  if (!user) return;

  try {
    await fetch('/auth/resend-confirmation', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ email: user.email }),
    });
    alert('Confirmation email resent! Please check your inbox.');
  } catch (e) {
    alert('Could not send email. Please try again later.');
  }
}

// ── NAVBAR RENDERER ───────────────────────────────────────────────────────────

/**
 * Builds the right-hand side of the navbar based on login state.
 *
 * NOT logged in:
 *   [Login]  [Register]
 *
 * Logged in (unconfirmed):
 *   👤 Name (unconfirmed)  [Logout]
 *
 * Logged in (confirmed, user):
 *   👤 Name  [Logout]
 *
 * Logged in (admin):
 *   ⚙ Name (admin)  [Dashboard]  [Logout]
 */
function renderNavbar() {
  const area = document.getElementById('nav-auth-area');
  if (!area) return;

  if (!isLoggedIn()) {
    area.innerHTML = `
      <a href="/login"    class="nav-btn">
        <i class="bi bi-box-arrow-in-right"></i> Login
      </a>
      <a href="/register" class="nav-btn nav-btn-solid">
        <i class="bi bi-person-plus"></i> Register
      </a>`;
    return;
  }

  const user = getUser();
  const name = user?.name || 'User';
  const roleClass = isAdmin() ? 'admin' : '';

  area.innerHTML = `
    <div class="user-badge">
      <span class="role-dot ${roleClass}"></span>
      ${isAdmin() ? '⚙ ' : '👤 '} ${name}
      ${!isConfirmed() ? '<span class="badge bg-warning text-dark ms-1" style="font-size:.7rem">unconfirmed</span>' : ''}
    </div>
    ${isConfirmed() ? `
      <button class="nav-btn nav-btn-solid" onclick="showSection('add')">
        <i class="bi bi-plus-lg"></i> Add Café
      </button>` : ''}
    <a href="/profile" class="nav-btn">
      <i class="bi bi-person-circle"></i> Profile
    </a>
    ${isAdmin() ? `<a href="/admin" class="nav-btn"><i class="bi bi-speedometer2"></i> Dashboard</a>` : ''}
    <button class="nav-btn" onclick="logout()">
      <i class="bi bi-box-arrow-right"></i> Logout
    </button>`;
}

// ── SHOW CONFIRMATION BANNER ──────────────────────────────────────────────────

function showConfirmBanner() {
  if (isLoggedIn() && !isConfirmed()) {
    // Use the wrapper div (confirm-banner-wrap) not the inner div
    const wrap = document.getElementById('confirm-banner-wrap');
    if (wrap && !sessionStorage.getItem('bannerDismissed')) {
      wrap.style.display = 'block';
    }
  }
}

// ── AUTO-RUN ON EVERY PAGE ────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  renderNavbar();
  showConfirmBanner();

  // Sync mobile menu with desktop nav on load
  // (in case menu is pre-opened or for accessibility)
  const desktopArea = document.getElementById('nav-auth-area');
  const mobileArea  = document.getElementById('mobile-auth-area');
  if (desktopArea && mobileArea) {
    // Use MutationObserver to sync mobile menu whenever desktop nav changes
    const observer = new MutationObserver(() => {
      const menu = document.getElementById('mobile-nav-menu');
      if (menu && menu.style.display !== 'none') {
        mobileArea.innerHTML = desktopArea.innerHTML;
      }
    });
    if (desktopArea) {
      observer.observe(desktopArea, { childList: true, subtree: true });
    }
  }
});
