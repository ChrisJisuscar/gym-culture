# Custom Lab: Oversize

## Conversión e inspección

Entrada: `frontend/static/models/Low_T-shirt.fbx` (287.920 bytes).
Salida: `frontend/static/models/oversized.glb` (979.968 bytes).
Se usaron `FBXLoader` y `GLTFExporter` de Three.js **0.160.0**, la misma
revisión del visor. No se instala un cargador FBX en producción.

Desde la raíz del repositorio:

```powershell
npm install --prefix .venv/custom-lab-tools --no-audit --no-fund --ignore-scripts three@0.160.0 playwright gltf-validator
node tools/custom-lab/convert-oversized.mjs
```

`oversized-inspection.json` registra hash SHA-256 de la entrada, materiales,
grupos de caras, límites UV, bounding boxes y resultado de glTF Validator.

| Propiedad | FBX / GLB |
| --- | --- |
| Mallas | Una: `Low_T_shirt1Mesh` |
| Geometría de origen | 5.355 posiciones, 5.097 polígonos |
| Geometría triangulada | 10.192 triángulos; 30.576 vértices no indexados |
| Atributos conservados | POSITION, NORMAL, TEXCOORD_0 |
| Materiales originales | Collar_Stand_FRONT_3154, Base_FRONT_3160, Patch_FRONT_3166 |
| Texturas conectadas | Ninguna; tampoco imágenes embebidas |
| Bounding box original mínimo | (-371,978607; 931,976013; -157,391418) |
| Bounding box original máximo | (376,942657; 1634,913086; 180,738647) |
| Orientación | Y arriba, frente +Z; sin rotación adicional |
| Escala aplicada | 0,0014226024473034068; altura visual normalizada a 1 |
| Dimensiones finales | 1,065417 × 1 × 0,481025 |
| Bounding box final | ±(0,532709; 0,5; 0,240512) |
| GLB final | Una escena, tres nodos, una malla, una primitiva, un material; sin texturas ni animaciones |

El FBX declara `UnitScaleFactor = 1` y Y arriba. La normalización es para
coordenadas del visor; no afirma medidas físicas ni una talla comercial.
Las UVs originales se conservan, incluyendo valores fuera de 0–1
(máximos U=1019,295593 y V=1591,738525). No se hace un unwrap nuevo.
Los decals siguen usando su proyección geométrica existente.

## Origen de las marcas y material final

Este archivo **no contiene mapas baseColor, normal/bump ni roughness/metallic**.
No se encontraron gráficos o logos horneados en texturas. Dos materiales son
grises y el material `Patch` es más claro: esa diferencia de color se elimina
al consolidarlos en un solo `MeshStandardMaterial` opaco, blanco configurable,
`metalness: 0`, `roughness: 0.88`, `DoubleSide`, sin mapas ni vertex colors.
El visor aplica el mismo material de tela a ambas prendas.

La comparación en Chrome del FBX original y del material uniforme, por delante
y por detrás, muestra pliegues y costuras de la propia geometría/normales, sin
estampados visibles. No se eliminaron caras ni se suavizó o deformó la malla.

**Límite geométrico:** `Patch_FRONT_3166` es una pieza real de 16 triángulos
junto al cuello, aproximadamente X=-19,26..29,42, Y=1571,21..1594,87,
Z=-118,03..-108,72 en coordenadas originales. Su color queda uniforme, pero
su relieve permanece. Si se requiere eliminar también ese borde físico, debe
editarse en Blender, revisar la superficie del cuello y reexportar. El pipeline
no oculta geometría ni promete borrar costuras/pliegues mediante materiales.

La validación del GLB produjo **0 errores y 0 advertencias**. Solo informa que
TEXCOORD_0 no es utilizado por el material liso; se conserva deliberadamente.

## Integración

- `garments.js` centraliza URL, etiqueta, disponibilidad y uso de variantes base.
  `state.garmentType` identifica la prenda activa. Hoodie carece de URL y se
  rechaza también desde la API JS, además de tener el botón deshabilitado.
- El selector vive dentro de la columna central. Se conservan los paneles
  PERSONALIZACIÓN y TU REMERA, con navegación por teclado y reduced-motion.
- Al cambiar con diseños o un diseño pendiente se pide exactamente:
  “Cambiar de prenda eliminará los diseños actuales.” Cancelar conserva todo.
- Se prepara el nuevo GLB antes de retirar el anterior. Un fallo de red deja
  intactos el modelo, el tipo y los diseños anteriores. La operación está
  bloqueada contra cambios simultáneos; no se precargan ambos modelos.
- Al confirmar y completar la carga se liberan decals, texturas, materiales
  y geometría anteriores. Se actualiza el tamaño del mismo DesignManager.
  Las lecturas/restauraciones de imágenes invalidan sus resultados si se
  liberaron sus recursos durante la operación.
- Escena, cámara, renderer, OrbitControls y animation loop se reutilizan.
  Box3 centra el modelo y reajusta distancias de cámara y controles. Resize
  recalcula el encuadre.
- Los previews frontal/trasero usan el **mismo renderer** temporalmente a
  1024×1024, pausan el render normal y ocultan el resaltado. Una cámara clonada
  calcula el encuadre cuadrado desde el tamaño activo. Finalmente se restauran
  resolución, color de fondo, selección y cámara interactiva.

## Persistencia y producto comercial

Se conserva el esquema `version: 1`. El backend acepta `tshirt` y `oversized`,
rechaza Hoodie/tipos desconocidos y mantiene todas las comprobaciones de
producto, variante, talla, color, stock, assets y propietario.
Las configuraciones antiguas `tshirt` conservan su modelo y coordenadas;
no se normalizó ni reemplazó su GLB. La restauración carga primero la prenda
indicada y luego restaura los diseños. No se transfieren coordenadas entre prendas.

El catálogo actual no tiene una asociación explícita prenda→ProductVariant.
La vista selecciona el primer producto activo; no se infiere que ese producto
sea Oversize a partir de su nombre. Por eso `oversized.usesBaseVariants` es
`false`: el editor no inventa precio/stock, devuelve `variantId: null` y
deshabilita la compra de Oversize. Color, talla visual, diseños, serialización
y previews sí funcionan. Al volver a Remera se recuperan las variantes reales.

El API puede guardar Oversize **cuando el cliente aporta una variante real y
coherente**; el tipo es visual y no modifica el catálogo. Vincular comercialmente
Oversize en la UI sigue pendiente y debe hacerse con datos reales. No se cambian
checkout, pagos ni backoffice.

## Verificación

```powershell
# Desde backend:
..\.venv\Scripts\python.exe manage.py check
..\.venv\Scripts\python.exe manage.py test customizations cart products --noinput
..\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8765 --noreload

# Desde la raíz, con el servidor iniciado:
node tools/custom-lab/browser-tests.cjs
git diff --check
```

Las pruebas de navegador usan Chrome local; `CHROME_PATH` permite elegir otro
ejecutable y `LAB_URL` otra dirección del servidor. Las solicitudes de escritura
al carrito se simulan, sin insertar datos en la base de desarrollo. Los tests
Django sí verifican la persistencia real en una base temporal de pruebas.

El script inspecciona objetos internos únicamente mediante una respuesta JS
instrumentada en Playwright; la aplicación no publica una API de depuración.
Comprueba cambio ida/vuelta, color, material, confirmación/cancelación, fallos
de carga, restauración de texto e imágenes, orbit/zoom, resize a móvil,
previews con contenido y sin recortes, carrito y liberación de recursos.
También comprueba identidad de escena/cámara/renderer/controles y un único
requestAnimationFrame del visor. Guarda previews de prueba bajo `.venv/`.

Resultados de esta implementación:

- `manage.py check`: sin problemas.
- `manage.py test customizations cart products --noinput`: **39 tests aprobados**.
- `node tools/custom-lab/browser-tests.cjs`: todos los grupos aprobados, sin
  errores JavaScript no controlados. Incluye cierre del visor durante una carga.
- Tras cuatro cambios adicionales: una geometría activa y cero texturas
  residuales, manteniendo el mismo motor y un solo animation loop.
- `git diff --check`: sin errores de whitespace.

## Archivos de esta tarea

Modificados:

- `frontend/templates/create_tshirt.html`
- `frontend/static/css/customizer.css`
- `frontend/static/js/customizer.js`
- `frontend/static/js/customizer-3d.js`
- `frontend/static/js/customizer-3d/design-manager.js`
- `backend/customizations/validators.py`
- `backend/customizations/tests.py`

Agregados:

- `frontend/static/models/oversized.glb`
- `frontend/static/js/customizer-3d/garments.js`
- `frontend/static/js/customizer-3d/garment-model.js`
- `tools/custom-lab/convert-oversized.mjs`
- `tools/custom-lab/oversized-inspection.json`
- `tools/custom-lab/browser-tests.cjs`
- `tools/custom-lab/README.md`

El FBX de entrada y los cambios preexistentes de otras secciones se conservaron.
