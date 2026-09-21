# Custom Lab: biblioteca, historial y herramientas

## Arquitectura

- `SavedDesign` guarda nombre, propietario y fechas y referencia una única `Customization` editable. El estado, producto, variante, imágenes y previews siguen usando el modelo y el serializador existentes; no hay una segunda representación de la personalización.
- Los borradores y las imágenes generadas se almacenan bajo `PRIVATE_MEDIA_ROOT` (`backend/var/private`), fuera de `MEDIA_ROOT`. Los endpoints de descarga comprueban ownership, requieren JWT y responden con `private, no-store`. No publicar ese directorio con el servidor web. Los archivos comerciales existentes conservan sus rutas.
- Guardar, restaurar, editar recomendaciones y agregar al carrito comparten `customization-api.js`, `DesignManager` y la serialización v1. El cliente conserva copias locales de las imágenes para que reemplazar archivos al guardar no rompa deshacer. Agregar un borrador al carrito crea una personalización comercial independiente.
- Los nuevos módulos separan historial, capas, transformaciones, calidad, biblioteca y generación. El motor existente conserva su única escena/render loop; estas funciones no agregan RAF ni timers de animación.

## Estado y edición

Se agregaron campos opcionales `layerOrder`, `visibility`, `flipX`, `flipY`, dimensiones originales/activas y `printQuality`. Las personalizaciones v1 anteriores siguen admitidas: el orden del array es el orden inicial, las capas son visibles y no están reflejadas por defecto.

`HistoryManager` mantiene hasta 60 acciones, serializadas y sin objetos Three.js. Las imágenes se internan una sola vez entre snapshots. Un drag genera una acción; entradas continuas de texto/rango se agrupan. Deshacer/rehacer restaura prenda, variante, color, capucha, imágenes originales/procesadas y todas las capas. El historial no se guarda en el servidor. Los atajos ignoran campos de escritura y diálogos abiertos.

Las capas modifican `renderOrder` y `visible` del mesh real. Se ordenan con botones subir/bajar/frente/fondo; no se implementó drag & drop opcional. Duplicar asigna un ID nuevo, clona la textura y proyecta una posición cercana válida. Los reflejos cambian UVs, sin alterar el archivo. Alinear calcula el torso desde el bounding box de la geometría visible y vuelve a proyectar sobre la superficie frontal o trasera; están implementados horizontal, vertical y centro de impresión.

## Calidad de impresión

La fuente de configuración es `customizations/print_quality.py`, expuesta en `editor-config` para usar la misma estimación en la UI. PPI efectivo = píxeles activos / dimensión de impresión en pulgadas, usando el menor valor entre ancho y alto. Alta >= 300, media >= 150, baja < 150; no bloquea guardar ni comprar.

La conversión usa la altura de los GLB suministrados (tshirt 28.06645584 unidades; oversized/hoodie 1 unidad) y alturas orientativas de prenda de 70/76/72 cm. Es una aproximación, no una medida industrial ni una calibración por talla. Al reemplazar modelos o conocer medidas de producción, ajustar `CUSTOM_LAB_PRINT_PROFILE` en settings con la estructura de `DEFAULT_PRINT_PROFILE`. El backend verifica las dimensiones del archivo y recalcula los metadatos; no confía en la estimación enviada por el cliente. Un derivado reducido utiliza su resolución efectiva, conservando también las dimensiones del original.

## Endpoints

| Ruta | Método | Uso |
| --- | --- | --- |
| `/mis-disenos/` | GET | Biblioteca del usuario, con login y cards |
| `/api/saved-designs/` | GET / POST | Lista paginada (24) / guardar estado completo multipart |
| `/api/saved-designs/<uuid>/` | GET / PATCH / DELETE | Leer / editar o renombrar / eliminar propio |
| `/api/saved-designs/<uuid>/duplicate/` | POST | Copia independiente de estado, archivos y previews |
| `/api/customizations/<uuid>/assets/<uuid>/` | GET | Imagen protegida del propietario |
| `/api/customizations/<uuid>/previews/<side>/` | GET | Preview protegida, `front` / `back` |
| `/api/customizations/editor-config/` | GET | Perfil de impresión y disponibilidad IA, sin secretos |
| `/api/customizations/generate-image/` | POST | Generación autenticada |
| `/api/customizations/generated/<uuid>/` | GET | Resultado privado del propietario |

POST/PATCH de estado comparte los campos multipart de Customization: `product`, `variant`, `configuration`, `preview_front`, `preview_back`, `asset_<key>`, más `name`. Un borrador no admite `add_to_cart=true`. La UI pide confirmación antes de eliminarlo. El listado evita cargar los JSON completos; las consultas precargan las relaciones usadas.

## IA opcional

`ImageGenerationService` admite proveedores reemplazables. Se implementó un adaptador HTTP de backend, deshabilitado por defecto; no se instaló un modelo Diffusers/GPU ni se contrató un servicio externo.

Configuración del operador:

- `IMAGE_GENERATION_PROVIDER=http` para activar; `disabled` para desactivar.
- `IMAGE_GENERATION_URL` apunta a un servicio controlado por el operador (HTTPS o HTTP de loopback, apto para un servicio Diffusers local).
- `IMAGE_GENERATION_API_KEY` es opcional, solo backend; se envía como Bearer. Nunca llega al navegador.
- `IMAGE_GENERATION_TIMEOUT` y `IMAGE_GENERATION_MAX_BYTES` se ajustan en settings (30 segundos por operación de red y 10 MiB por defecto). Se comprueba también un plazo durante la lectura para evitar una respuesta indefinida por goteo; una lectura en curso puede consumir el timeout de socket restante.

Contrato del servicio: recibe JSON `{ "prompt": "...", "culture": "anime", "format": "square", "transparent": true }` y devuelve `{ "image_base64": "..." }`. No se siguen redirects ni URLs de imágenes del proveedor. Solo se aceptan PNG/JPEG/WebP, 64–2048 px por lado y tamaño limitado; el resultado se normaliza a PNG. La transparencia es una petición al proveedor, no una garantía.

Se guardan prompt, provider, opciones, archivo y fecha en `GeneratedImage`. Se exige usuario autenticado y se limita a 3 solicitudes por hora mediante el throttle de DRF. Para despliegues con varios workers usar un caché compartido de Django para que el límite sea global. Errores del proveedor, timeout, resultado inválido y servicio deshabilitado tienen respuesta explícita. Usar el resultado pasa por `prepareImage`, igual que cualquier upload; quitar fondo, capas y persistencia no tienen un camino especial para IA.

## Archivos y migración

- Backend: `customizations/{models,serializers,validators,signals,urls,storage,saved_designs,print_quality,image_generation,generation_views,test_editor_workspace}.py`; integración en `config/{settings,urls,views}.py` y `recommendations/state.py`.
- Migración aplicada: `customizations/0003_customization_private_assets_and_more.py` (SavedDesign, GeneratedImage, almacenamiento privado).
- Frontend: `js/{editor-workspace,saved-designs,ai-generation,customization-api,customizer,customizer-3d,recommendation-admin}.js`; `js/customizer-3d/{design-manager,history-manager,layer-manager,transform-tools,print-quality}.js`; `css/editor-workspace.css`; templates `create_tshirt.html`, `saved_designs.html`, `components/{navbar,editor-dialogs}.html`.
- QA: `workspace-tests.cjs`, `history-tests.cjs`; `session-fixture.cjs` limpia primero los items comerciales de las cuentas efímeras de prueba. Capturas: `workspace-desktop.png`, `workspace-mobile.png`, `saved-designs-desktop.png`.

## Verificación

Auditoría del 21/09/2026: **266 tests Django aprobados**; `check`, `makemigrations --check --dry-run`, `git diff --check` y sintaxis de JavaScript sin errores. Pasaron `history-tests.cjs`, `workspace-tests.cjs`, `browser-tests.cjs`, `showroom-tests.cjs` y `background-tests.cjs`. Las cuentas y datos temporales de estas pruebas fueron eliminados.

Ejecutar desde `backend`: `../.venv/Scripts/python.exe manage.py check`, `manage.py test --noinput`, `manage.py makemigrations --check --dry-run`. Desde raíz: `git diff --check`, `node tools/custom-lab/history-tests.cjs`, `node tools/custom-lab/workspace-tests.cjs` (Django en 127.0.0.1:8765; Playwright y Chrome locales).

La suite de workspace prueba APIs reales para guardar, listar, previews privadas, editar, duplicar, confirmar/cancelar eliminación, restaurar transparencia y transformaciones, y conservar carrito al borrar el borrador. Comprueba undo/redo y shortcuts, drag agrupado, texto, duplicación, flips, alineación en tres prendas, escala/PPI, capucha y capas reales. La integración de generación usa una respuesta controlada porque el proveedor real está deshabilitado; los tests Django cubren provider success/error/timeout, validación y permisos. Capturas y comprobación de overflow en desktop y viewport móvil, con consola sin errores JS.

También se ejecutan las regresiones existentes `browser-tests.cjs`, `showroom-tests.cjs` y `background-tests.cjs`: cambios de modelos y recursos, carrito, recomendaciones públicas/Backoffice, escena/RAF únicos y quitar fondo. Las comprobaciones móviles usan emulación en Chrome, no un dispositivo físico.

Pendientes reales de despliegue: conectar y evaluar un proveedor de generación si se desea habilitar IA; calibrar medidas físicas de impresión con prendas reales. El historial es de sesión y no sobrevive a recargar, aunque el estado guardado sí.
