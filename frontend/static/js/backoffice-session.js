// Administrative requests use Django's session and CSRF, never customer tokens.
(() => {
  const loginUrl = () => `/backoffice/login/?next=${encodeURIComponent(location.pathname + location.search)}`;
  const redirectToLogin = () => location.assign(loginUrl());
  const csrfToken = () => document.querySelector('meta[name="csrf-token"]')?.content
    || document.querySelector('[name="csrfmiddlewaretoken"]')?.value
    || decodeURIComponent(document.cookie.match(/(?:^|; )csrftoken=([^;]*)/)?.[1] || '');
  const request = async (url, options = {}) => {
    const target = new URL(url, location.origin);
    if (target.origin !== location.origin) throw new Error('La solicitud administrativa debe usar el mismo sitio.');
    const headers = new Headers(options.headers || {});
    headers.delete('Authorization');
    if (!['GET', 'HEAD', 'OPTIONS'].includes(String(options.method || 'GET').toUpperCase())) headers.set('X-CSRFToken', csrfToken());
    const response = await fetch(target, { ...options, credentials: 'same-origin', headers });
    if (response.status === 401 || response.status === 403) {
      const data = await response.clone().json().catch(() => ({}));
      if (data.code === 'session_required') {
        redirectToLogin();
        throw Object.assign(new Error('Tu sesión administrativa expiró. Volvé a ingresar.'), { status: 401 });
      }
    }
    return response;
  };
  const requestJson = async (url, options = {}) => {
    const response = await request(url, options);
    if (response.status === 204) return null;
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw Object.assign(new Error(data.detail || Object.values(data).flat(Infinity).join(' ') || 'No se pudo completar la operación.'), { status: response.status });
    return data;
  };
  window.backofficeRequest = request;
  window.GymCultureBackoffice = { request, requestJson, redirectToLogin, isSessionError: error => error.status === 401 };
})();
