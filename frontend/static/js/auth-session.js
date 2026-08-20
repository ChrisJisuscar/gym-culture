(() => {
  const keys = { access: 'gc_access_token', refresh: 'gc_refresh_token', user: 'gc_user' };
  const readUser = () => {
    try { return JSON.parse(localStorage.getItem(keys.user)); } catch { return null; }
  };
  const clear = () => Object.values(keys).forEach((key) => localStorage.removeItem(key));
  const save = ({ access, refresh, user }) => {
    localStorage.setItem(keys.access, access);
    localStorage.setItem(keys.refresh, refresh);
    localStorage.setItem(keys.user, JSON.stringify(user));
  };
  const formatJoinedDate = (value) => {
    if (!value) return '—';
    const date = new Date(value);
    return Number.isNaN(date.getTime()) ? '—' : new Intl.DateTimeFormat('es-AR', {
      day: '2-digit', month: 'long', year: 'numeric'
    }).format(date);
  };
  const setProfileOpen = (open) => {
    const trigger = document.querySelector('#nav-auth');
    const menu = document.querySelector('#nav-user-menu');
    if (!trigger || !menu) return;
    menu.hidden = !open;
    trigger.setAttribute('aria-expanded', String(open));
  };
  const refreshAccess = async () => {
    const refresh = localStorage.getItem(keys.refresh);
    if (!refresh) throw new Error('No hay sesión.');
    const response = await fetch('/api/auth/refresh/', {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh })
    });
    if (!response.ok) throw new Error('La sesión expiró.');
    const data = await response.json();
    localStorage.setItem(keys.access, data.access);
    return data.access;
  };
  const request = async (url, options = {}, retried = false) => {
    const access = localStorage.getItem(keys.access);
    const headers = new Headers(options.headers || {});
    if (access) headers.set('Authorization', `Bearer ${access}`);
    const response = await fetch(url, { ...options, headers });
    if (response.status === 401 && !retried && localStorage.getItem(keys.refresh)) {
      try { await refreshAccess(); return request(url, options, true); } catch { clear(); updateNavbar(); }
    }
    return response;
  };
  const updateNavbar = () => {
    const user = readUser();
    const navAuth = document.querySelector('#nav-auth');
    const mobileAuth = document.querySelector('#mobile-auth');
    const mobileLogout = document.querySelector('#mobile-logout-button');
    const mobileProfile = document.querySelector('#mobile-profile');
    const loginButton = document.querySelector('#nav-login-button');
    [navAuth, mobileAuth].filter(Boolean).forEach((link) => {
      link.dataset.authenticated = Boolean(user);
      if (link.tagName === 'A') link.href = user ? '#' : '/login/';
      link.setAttribute('aria-label', user ? `Abrir perfil de ${user.username}` : 'Iniciar sesión');
      link.title = user ? `Abrir perfil: ${user.username}` : 'Iniciar sesión';
      if (link.id === 'nav-auth') link.querySelector('.nav-user-label').textContent = user ? user.username.toUpperCase() : 'LOGIN';
      else link.textContent = user ? `Perfil (${user.username})` : 'Login';
    });
    if (mobileLogout) mobileLogout.hidden = !user;
    if (loginButton) {
      loginButton.hidden = false;
      loginButton.textContent = user ? 'Cerrar sesión' : 'Iniciar sesión';
      loginButton.dataset.authenticated = Boolean(user);
      loginButton.setAttribute('aria-label', user ? 'Cerrar sesión' : 'Iniciar sesión');
    }
    if (!user && mobileProfile) mobileProfile.hidden = true;
    document.querySelector('#nav-profile-username')?.replaceChildren(document.createTextNode(user?.username || '—'));
    document.querySelector('#nav-profile-email')?.replaceChildren(document.createTextNode(user?.email || '—'));
    document.querySelector('#nav-profile-joined')?.replaceChildren(document.createTextNode(formatJoinedDate(user?.date_joined)));
    document.querySelector('#mobile-profile-username')?.replaceChildren(document.createTextNode(user?.username || '—'));
    document.querySelector('#mobile-profile-email')?.replaceChildren(document.createTextNode(user?.email || '—'));
    document.querySelector('#mobile-profile-joined')?.replaceChildren(document.createTextNode(`Miembro desde ${formatJoinedDate(user?.date_joined)}`));
    if (!user) setProfileOpen(false);
  };
  const logout = async () => {
    const refresh = localStorage.getItem(keys.refresh);
    if (refresh && localStorage.getItem(keys.access)) {
      await request('/api/auth/logout/', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ refresh }) }).catch(() => {});
    }
    clear();
    updateNavbar();
    window.location.assign('/');
  };
  const hydrate = async () => {
    if (!localStorage.getItem(keys.access) && !localStorage.getItem(keys.refresh)) return updateNavbar();
    try {
      const response = await request('/api/auth/me/');
      if (!response.ok) throw new Error('Sesión inválida.');
      localStorage.setItem(keys.user, JSON.stringify(await response.json()));
    } catch { clear(); }
    updateNavbar();
  };
  window.GymCultureAuth = { clear, hydrate, logout, request, save, updateNavbar };
  document.addEventListener('DOMContentLoaded', () => {
    updateNavbar();
    hydrate();
    const navAuth = document.querySelector('#nav-auth');
    const mobileAuth = document.querySelector('#mobile-auth');
    const mobileLogout = document.querySelector('#mobile-logout-button');
    const mobileProfile = document.querySelector('#mobile-profile');
    const loginButton = document.querySelector('#nav-login-button');
    navAuth?.addEventListener('click', (event) => {
      if (navAuth.dataset.authenticated !== 'true') return;
      event.preventDefault();
      const menu = document.querySelector('#nav-user-menu');
      setProfileOpen(Boolean(menu?.hidden));
    });
    mobileAuth?.addEventListener('click', (event) => {
      if (mobileAuth.dataset.authenticated !== 'true') return;
      event.preventDefault();
      event.stopPropagation();
      if (mobileProfile) mobileProfile.hidden = !mobileProfile.hidden;
    });
    mobileLogout?.addEventListener('click', logout);
    loginButton?.addEventListener('click', () => {
      if (loginButton.dataset.authenticated === 'true') logout();
      else window.location.assign('/login/');
    });
    document.querySelector('#nav-logout-button')?.addEventListener('click', logout);
    document.addEventListener('click', (event) => {
      if (!event.target.closest('.user-menu-wrap')) setProfileOpen(false);
      if (!event.target.closest('#mobile-profile') && !event.target.closest('#mobile-auth') && mobileProfile) mobileProfile.hidden = true;
    });
  });
})();
