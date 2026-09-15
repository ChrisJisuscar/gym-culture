# GYM CULTURE: cierre de recomendaciones, sesión admin y quitar fondo

Este documento describe la fase anterior. El estado actual, las verificaciones y las limitaciones del refinamiento posterior están en [REFINEMENT.md](REFINEMENT.md). En particular, el autoplay ya no tiene control manual y quitar fondo ahora usa un pipeline híbrido con segmentación local.

## Auditoría y alcance

Se continuó el árbol de trabajo existente, conservando las ediciones del usuario y las 36 recomendaciones iniciales. No se recrearon modelos ni escenas.

| Estado al inicio | Implementación |
| --- | --- |
| Correcto | Culture, DesignRecommendation, RecommendationAsset, filtros públicos, estado completo del Custom Lab, centro 3D + órbita DOM, selector de culturas, navegación y CTA |
| Correcto | Preview de quitar fondo, Aplicar/Cancelar, original separado, restauración y persistencia de transformaciones |
| Incompleto | Orden numérico, autenticación administrativa mezclada con JWT del cliente, editor con segundo control de identidad |
| A corregir | Quitar fondo demasiado restrictivo para calidad media/baja; reloj de animación limitado a 50 ms por frame |

## Backoffice y autenticación

- Nuevas rutas: `GET/POST /backoffice/login/` y `POST /backoffice/logout/`. Login acepta usuario o correo, llama a `authenticate`, exige cuenta activa ADMIN o is_staff y crea sesión Django con `login`. Logout usa CSRF y destruye solo la sesión administrativa.
- Middleware protege todas las páginas `/backoffice/`, incluido el editor. Anónimo redirige al login; cliente autenticado recibe 403. No se entrega el editor antes de autorizar.
- Todas las APIs Backoffice usan exclusivamente `SessionAuthentication` y permiso administrativo. Las escrituras administrativas del catálogo compartido también usan sesión. Las lecturas públicas y los endpoints autenticados del cliente conservan JWT.
- Un único `backofficeRequest` usa `credentials: same-origin`, elimina Authorization y agrega X-CSRFToken a las escrituras. Sin csrf_exempt. Sesión HttpOnly/SameSite=Lax; cookies Secure fuera de DEBUG. Respuestas administrativas no-store.
- El editor ya no consulta `/api/auth/me/` ni carga el helper JWT del cliente. Restaura, edita, guarda el mismo registro, genera preview WebP y permite volver al listado.

**Causa de auth:** la página y el editor dependían de identidades distintas; el segundo control usaba el JWT guardado por la tienda. Un JWT ausente, vencido o de cliente impedía reconocer al administrador. Ahora la autorización proviene de request.user y la sesión administrativa en servidor.

## Orden visual

El listado agrupa recomendaciones por cultura. Permite arrastrar con mouse/touch desde el asa, muestra la posición de destino y ofrece Subir/Bajar con nombres accesibles. No hay input numérico Orden. Los filtros mantienen las posiciones de los registros ocultos.

Se reutiliza `POST /api/backoffice/recommendations/reorder/` con:

```json
{"culture": 1, "ordered_ids": [4, 2, 1, 3], "expected_order": [1, 2, 3, 4]}
```

Los arrays representan **todos** los registros de esa cultura. Rechaza duplicados, IDs ajenos y listas incompletas. Un orden concurrente obsoleto devuelve 409 y la UI recarga el orden real. La transacción bloquea cultura y filas, escribe posiciones 1..N y devuelve 200 con ordered_ids/positions. Crear agrega al final; borrar y cambiar cultura normalizan las posiciones. Una restricción de BD impide duplicados por cultura.

Migraciones nuevas, **aplicadas localmente**:

- `0006_normalize_culture_order`: normaliza posiciones conservando el orden relativo y vuelve sort_order no editable.
- `0007_unique_culture_order`: agrega UniqueConstraint(culture, sort_order).

Se separó la transformación de datos de la restricción para evitar eventos de trigger pendientes en PostgreSQL. Las migraciones 0001–0005 corresponden a la implementación anterior. Otras instalaciones deben ejecutar `python manage.py migrate`.

## Showroom y reloj

Se mantiene una Scene, un WebGLRenderer, una cámara, un OrbitControls y un RAF compartidos con el Custom Lab. El canvas cambia de contenedor sin perder el borrador del editor. La órbita usa previews WebP y el reloj existente; no crea escenas por recomendación ni setInterval.

Rotación de **30 segundos por vuelta**, basada en delta real sin recortarlo por FPS. Pointerdown pausa; drag controla la órbita; al soltar hay inercia amortiguada, espera de 1.8 s y entrada progresiva de 1.2 s. Hover no pausa. Pointercancel, pérdida de captura/foco y liberación fuera del área no dejan dragging activo. Cambios de cultura/prenda y anterior/siguiente conservan autoplay.

Movimiento reducido lo desactiva por defecto; un control visible permite activarlo expresamente o pausarlo. Visibilitychange/pageshow reinician el reloj para evitar saltos tras volver a la pestaña. No se anima fuera de pantalla.

**Diagnóstico verificable:** antes de corregir, Chrome sin movimiento reducido ya avanzaba unos 120° en 10 s; el bloqueo total reportado no se reprodujo en ese entorno. Sí existía un límite de delta de 50 ms que alargaba la vuelta cuando bajaban los FPS. Se eliminó y se hizo explícita la dependencia del motor antes de suscribirse a su reloj. La prueba real a 5 FPS ahora avanzó 119.6° en 10 s.

Se conservaron previews de 240 px en escritorio, 176 en tablet y 150 en móvil, escala 0.86–1 y órbita separada del centro. En móvil el recorrido pasa debajo. Si el catálogo no cabe, se ocultan temporalmente las previews posteriores que se cruzarían; todas siguen accesibles con navegación. El selector conserva solo GYMRAT/ANIME/MEMES/URBANO, glow y transiciones, sin panel ni textos retirados.

## Quitar fondo

Se reutiliza `POST /api/customizations/remove-background/`, async desde la UI con “Procesando...”. No descarga modelos ni usa segmentación agresiva.

1. Valida PNG/JPEG/WebP (límites de upload existentes: 10 MB, 64–8192 px). Detecta alpha existente y deja la imagen intacta. Ya no rechaza imágenes válidas de 64–95 px. Mantiene la resolución hasta 3072 px de lado mayor; reduce imágenes mayores sin modificar el original guardado.
2. Analiza bandas, esquinas, ruido y variación en una muestra de hasta 512 px. Estima hasta tres colores próximos del mismo fondo, evitando incorporar tinta de otro color.
3. Compara CIE Lab con tolerancia adaptativa moderada, según variación, compresión y tamaño. No exige cuatro esquinas perfectas ni 92% de cobertura.
4. Repara pequeños huecos del contorno únicamente para proteger contenido y aplica flood fill de cuatro vecinos desde los bordes. Las zonas encerradas del mismo color permanecen opacas.
5. Valida contraste y existencia de sujeto/fondo. Si falla la máscara adaptativa, intenta una máscara más estricta. Calcula HIGH/MEDIUM/LOW; LOW solo produce preview si supera las validaciones de seguridad. UNSAFE no devuelve una imagen modificada.
6. Refina alpha y matte en un borde exterior muy pequeño, sin erosionar trazos sólidos ni zonas internas. Devuelve PNG transparente.

Respuesta 200: PNG, no-store, X-Background-Confidence y X-Background-Confidence-Level. Rechazo 422: detail/code/backgroundConfidence/confidenceLevel. Mensaje integrado:

> No pudimos quitar el fondo de esta imagen con suficiente precisión. Probá con una imagen donde el fondo contraste más con el diseño.

Transparencia existente informa que la imagen ya tiene transparencia. Se rechazan ruido fuerte, fondos complejos, gradientes importantes, contraste insuficiente y ausencia de exterior/sujeto identificable. Se mantiene el límite de 10 solicitudes/minuto y una operación concurrente por proceso.

**ANTES / DESPUÉS, Aplicar / Cancelar y Restaurar original** permanecen integrados. Ningún nivel aplica automáticamente. LOW/MEDIUM añaden orientación para revisar los detalles. Aplicar conserva originalSource/originalAssetId y activa source/assetId del derivado; mantiene design id, posición, escala y rotación. Carrito y recomendaciones persisten ambos assets cuando corresponde. Se liberan referencias y texturas sustituidas.

## Archivos de esta fase

| Área | Archivos nuevos/modificados |
| --- | --- |
| Sesión y permisos | backend/users/backoffice.py, users/permissions.py, users/views.py; backend/config/settings.py, config/urls.py; backend/orders/views.py, products/views.py, recommendations/views.py |
| Helper y acceso UI | frontend/static/js/backoffice-session.js, backoffice.js, customization-api.js, recommendation-admin.js; frontend/templates/base.html, create_tshirt.html, backoffice/base.html, login.html, auth_base.html, access_denied.html |
| Orden | backend/recommendations/models.py, ordering.py, serializers.py, state.py, admin.py, migrations/0006*, migrations/0007*; frontend/static/js/backoffice-recommendations.js; frontend/templates/backoffice/recommendations.html; frontend/static/css/backoffice.css |
| Reloj | frontend/static/js/customizer-3d.js, showroom-orbit.js, recommendations.js; frontend/templates/create_tshirt.html |
| Fondo | backend/customizations/background_removal.py, views.py; frontend/static/js/customizer.js, customizer-3d/background-removal-service.js, customizer-3d/design-manager.js; frontend/templates/create_tshirt.html |
| Tests | backend/users/test_backoffice.py, recommendations/test_ordering.py, recommendations/tests.py, products/tests.py, customizations/test_background_removal.py |
| QA | tools/custom-lab/session-fixture.cjs, admin-session-tests.cjs, showroom-autoplay-tests.cjs, showroom-tests.cjs, background-tests.cjs, background-fixtures.py, capturas y este informe. Los antiguos scripts Backoffice y upgrade-recommendation-states.cjs se adaptaron a sesión. |

El árbol incluye además los archivos de la fase anterior de recomendaciones. No se modificó el vendor OrbitControls.js.

## Verificación realizada

- **248 tests Django aprobados**, suite completa desde backend; check sin errores, makemigrations --check --dry-run sin cambios, migraciones aplicadas y git diff --check limpio.
- `admin-session-tests.cjs`: login real administrador/cliente rechazado, logout, cookie HttpOnly/Lax, CSRF, JWT cliente independiente, carga de todas las secciones, reorder mouse/touch, recarga, Subir/Bajar, culturas independientes, edición/preview/guardado sin Authorization. Sin errores JS ni HTTP inesperados.
- `showroom-autoplay-tests.cjs`: diez segundos reales sin interacción en escritorio/móvil; pausa durante drag, reanudación, anterior/siguiente, cultura, prenda y movimiento reducido. Un RAF/Scene/Renderer/Controls. Prueba adicional a 5 FPS; no depende de invocar manualmente el callback de animación.
- `showroom-tests.cjs`: rotación del centro 360°, clic en previews, navegación, CTA editable, borrador intacto, capas y capucha, CRUD real por sesión, móvil/vacío y memoria acotada.
- `showroom-layout.cjs`: 72 ángulos, tres prendas y anchos 1440/900/390/320 px; sin cruces de previews visibles ni obstrucción del modelo.
- `background-tests.cjs`: preview sin mutación, Cancelar/Aplicar, persistencia de original/derivado, alpha y transformaciones restauradas, Restaurar original después de guardar. Logo, blancos internos, JPEG, 64 px, WebP, gris, color, ruido leve; complejo/contraste insuficiente/PNG transparente intactos. Se respeta el throttle real.
- `browser-tests.cjs`: regresión del Custom Lab cliente, cambios de prenda, materiales, previews, imágenes, carrito y recursos; sin errores JS.
- Capturas inspeccionadas del showroom desktop/móvil, reorder desktop/móvil, login, editor administrativo y Antes/Después. El informe visual background-removal-cases.png incluye todos los casos A–J solicitados más ruido leve; sus letras conservan la nomenclatura de fixtures previa.

Reproducir con Django local en 127.0.0.1:8765 y Playwright/Chrome instalados:

```powershell
# Desde backend
..\.venv\Scripts\python.exe manage.py check
..\.venv\Scripts\python.exe manage.py test --noinput
..\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run
# Desde la raíz
git diff --check
.venv\Scripts\python.exe tools/custom-lab/background-fixtures.py
node tools/custom-lab/admin-session-tests.cjs
node tools/custom-lab/showroom-autoplay-tests.cjs
node tools/custom-lab/showroom-tests.cjs
node tools/custom-lab/showroom-layout.cjs
node tools/custom-lab/background-tests.cjs
node tools/custom-lab/browser-tests.cjs
```

Las pruebas nuevas crean y eliminan sus propios usuarios y registros temporales, sin imprimir credenciales ni modificar administradores existentes. La suite antigua del editor intercepta sus escrituras de cliente.

## Límites reales

No quedan criterios funcionales pendientes en el entorno local probado. Mobile/touch se verificó con Chrome emulado y CDP; no se midió rendimiento en teléfonos físicos. El algoritmo conserva antes que destruir y puede rechazar imágenes válidas; no promete recortar fotos complejas ni separar colores indistinguibles. Salida máxima 3072 px, original intacto. Se requiere WebGL para el centro 3D. No se desplegó a producción.
