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
    [navAuth, mobileAuth].filter(Boolean).forEach((link) => {
      link.dataset.authenticated = Boolean(user);
      link.href = user ? '#' : '/login/';
      link.setAttribute('aria-label', user ? `Cerrar sesión de ${user.username}` : 'Iniciar sesión');
      link.title = user ? `Cerrar sesión: ${user.username}` : 'Iniciar sesión';
      if (link.id === 'nav-auth') link.querySelector('.nav-user-label').textContent = user ? user.username.toUpperCase() : 'LOGIN';
      else link.textContent = user ? `Salir (${user.username})` : 'Login';
    });
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
    document.querySelectorAll('#nav-auth, #mobile-auth').forEach((link) => link.addEventListener('click', (event) => {
      if (link.dataset.authenticated === 'true') { event.preventDefault(); logout(); }
    }));
  });
})();
