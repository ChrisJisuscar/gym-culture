# Verificación del refinamiento de GYM CULTURE

Se revisaron los siete puntos del último pedido sobre la implementación existente, las rutas y permisos de backend, la persistencia, los módulos JavaScript y la suite completa del proyecto. Se conservaron las modificaciones previas y los datos del catálogo. No se modificó el archivo vendor `OrbitControls.js`.

## Resultado por área

| Área | Implementación y evidencia |
| --- | --- |
| Showroom | Un único Scene/Renderer/Camera/OrbitControls/RAF compartido con el editor. Órbita DOM basada en deltaTime, 30 segundos por vuelta, sin controles manuales de autoplay. Drag pausa; liberación conserva inercia y recupera velocidad progresivamente. Click, anterior/siguiente y cambios de cultura/prenda mantienen movimiento. |
| Previews | Se conservaron tamaños de 240/176/150 px según viewport, escala 0.86–1 y profundidad. En móvil orbitan debajo del centro. Los elementos posteriores que se cruzarían se ocultan temporalmente; navegación mantiene acceso a todos. |
| Culturas y navbar | Selector debajo del Custom Lab y encima del showroom, sin caja ni textos antiguos. TIENDA va a `/#home`. CULTURAS va a `/crear-mi-remera/#culturas`, donde realmente vive el Custom Lab; desde esa página hace scroll suave. No se duplicó el Lab en Home. |
| Oversize | Suavizado de profundidad localizado en el torso, sin alterar coordenadas x/y de la silueta, cuello o mangas. La misma geometría visual se usa para proyectar. Normales interpoladas y transformadas correctamente al espacio mundial; editor y showroom reutilizan la preparación. |
| Texto | La generación de texturas ahora ajusta uniformemente el tamaño de fuente al ancho disponible. Antes, limitar el canvas a 2048 px recortaba caracteres largos antes de proyectarlos, incluso con cobertura geométrica completa. |
| Zoom | Distancia mínima más cercana, limitada además por el radio real de los vértices y un margen. Conserva rotación/damping; rueda y pinch verificados en Chrome. |
| Backoffice y persistencia | CRUD, activación, filtros, preview, orden mouse/touch, sesión/CSRF y editor compartido pasaron las pruebas. Se conserva el ID del diseño y sus transformaciones al aplicar/restaurar recortes. |

La instrucción más reciente exige autoplay permanente y elimina los controles: el movimiento orbital continúa también bajo `prefers-reduced-motion`. Las otras transiciones mantienen su tratamiento de movimiento reducido. Se suspende el trabajo fuera de pantalla/pestaña oculta para ahorrar recursos.

GYMRAT + Remera Clásica tiene actualmente una sola recomendación activa. Ocupa el centro y no quedan elementos que orbiten: es un estado del catálogo, no un autoplay detenido. No se cambiaron las activaciones del usuario.

## Quitar fondo: estrategia final

Se reutiliza `POST /api/customizations/remove-background/`; no hay servicio de pago ni claves externas.

1. Validación de formato real/MIME, 10 MB y 64–8192 px. Alpha existente se conserva sin procesar. La salida se limita a 3072 px de lado mayor; el original permanece intacto.
2. Clasificación aproximada por estructura, paleta y bordes. Logos y gráficos planos con exterior medible mantienen el algoritmo rápido: distancia CIE Lab, tolerancia adaptativa moderada y flood fill conectado al exterior. Conserva regiones internas desconectadas del fondo.
3. Personajes, fotografías y contenido estructurado usan **BiRefNet Lite ONNX local en CPU**. El modelo separa el sujeto por sus características aprendidas. No se ejecuta código remoto ni se descarga nada durante una solicitud. Fuentes: [modelo ONNX y licencia MIT](https://huggingface.co/onnx-community/BiRefNet_lite-ONNX), [proyecto BiRefNet](https://github.com/ZhengPeng7/BiRefNet).
4. Validación de extensión del sujeto, regiones seguras de foreground/background, fragmentación, huecos internos inciertos, opacidad del interior e incertidumbre global. Rechaza resultados inseguros; si falta el modelo avanzado, informa indisponibilidad sin sustituirlo por un recorte agresivo por color.
5. Refina alpha conservando bordes suaves y núcleos opacos. Descontamina bordes solo cuando hay evidencia de fondo cercano; no aplica erosión general ni rellena huecos que el modelo identifica claramente como fondo.
6. El resultado aparece en una comparación de hasta **1080 px**, con checkerboard, imágenes `contain` sin ampliación artificial, vista de píxeles reales y desplazamiento. Aplicar requiere confirmación. “Revisar recorte” permite volver a comparar la versión aplicada y restaurar el original desde el panel. Cancelar no cambia el diseño.

Se rechazan ausencia de sujeto, contraste insuficiente, ruido sin estructura, máscaras diminutas/casi completas, fragmentación excesiva, grandes huecos inciertos e incertidumbre elevada. Mensaje integrado:

> No pudimos separar el fondo de este diseño con suficiente precisión. Probá con una imagen de mayor calidad o con mayor contraste entre el diseño y el fondo.

PNG con alpha existente tiene un mensaje específico y queda intacto. La confianza es una heurística de seguridad, no una probabilidad garantizada de acierto semántico.

### Preparación del motor

Instalar `requirements.txt` y ejecutar desde `backend`:

```powershell
..\.venv\Scripts\python.exe manage.py prepare_background_removal --download
```

Modelo verificado localmente: `backend/var/models/birefnet-general-lite.onnx`, 224005088 bytes, SHA256 `5600024376f572a557870a5eb0afb1e5961636bef4e1e22132025467d0f03333`. Ruta opcional mediante `BACKGROUND_REMOVAL_MODEL_PATH`. El archivo está excluido de Git y debe prepararse en otra instalación. El comando descarga con reanudación, límite de reintentos y validación de integridad antes de activarlo.

La inferencia reutiliza una sesión perezosa, dos hilos de CPU y un bloqueo por proceso. Se desactivó la retención de grandes arenas de memoria de ONNX. La UI permanece disponible con “Procesando...”.

## Verificación realizada

- **254 tests Django aprobados**, suite completa desde `backend`, 255.816 s. Incluye productos, usuarios, pedidos, pagos, carrito, personalizaciones y recomendaciones. Los logs de errores simulados pertenecen a pruebas de fallo controlado.
- `python manage.py check`: sin problemas.
- `python manage.py makemigrations --check --dry-run`: sin cambios. Esta fase no añade migraciones.
- `python manage.py prepare_background_removal`: algoritmo simple y checksum del modelo verificados.
- `git diff --check`: aprobado; Git solo informó conversiones habituales LF/CRLF.
- Sintaxis de los **26 módulos JavaScript** propios: aprobada.
- `showroom-autoplay-tests.cjs`: 120.4°/10 s desktop, 120.2°/10 s mobile y 119.6°/10 s a 5 FPS. Drag/release, previo/siguiente, cultura/prenda y una sola escena/RAF aprobados.
- `showroom-tests.cjs`: intercambio del centro, giro del modelo, CTA, borrador conservado, memoria acotada, filtros, vacío, mobile y CRUD real del editor administrativo; sin errores JS.
- `refinement-tests.cjs`: cinco diseños (cuadrado, texto, vertical, ancho, transparente), cinco posiciones y tres combinaciones de escala/rotación: **75 casos**, cobertura mínima 99.98%. Estado restaurado e ID conservado. Proyección inválida conserva geometría/estado anteriores. Textos de hasta 50 caracteres no se cortan en sus texturas. Zoom de tres prendas, pinch real mediante CDP y navbar desktop/mobile aprobados.
- `projection-audit.cjs final`: 15 posiciones adicionales, incluyendo laterales inferiores; cobertura UV completa. Se inspeccionó la captura lateral después de corregir también la textura de texto.
- `background-tests.cjs`: originales/derivados separados, Cancelar/Aplicar/Revisar/Restaurar, persistencia del alpha y transformaciones, modal ancho y fuentes pequeñas sin ampliación; sin errores JS.
- `semantic-qa.py`: inferencia **real, sin mocks**, en tres ilustraciones anime, dos fotografías y un animal. Comparaciones inspeccionadas en [semantic-comparison.png](semantic-comparison.png).
- `semantic-browser-tests.cjs`: endpoint semántico real, UI disponible mientras procesa, comparación desktop/mobile, inspección 1:1, confirmación y restauración; sin errores JS. Flujo completo medido en unos 40 s.
- `browser-tests.cjs`: regresión del editor, carga/disposición, cambio de prenda, materiales, carrito y restauración ante fallo de carga.
- `admin-session-tests.cjs`: todas las secciones Backoffice, sesiones, cliente rechazado, CSRF, JWT independiente, reorder mouse/touch, recarga y editor; sin errores JS/HTTP inesperados.

### Matriz de quitar fondo

| Caso solicitado | Comprobación |
| --- | --- |
| Negro sobre blanco; blanco sobre negro; color sólido | Unit tests y fixtures A, I, J; tinta preservada. |
| JPG comprimido; resolución media/baja | Fixture D, JPEG/WebP comprimido y G de 64 px; interiores conservados. |
| Anime con fondo complejo | Tres imágenes reales; ropa, piel y accesorios separados. |
| Ropa de color parecido al fondo | Anime azul sobre ciudad azul; máscara semántica conserva chaqueta, falda y bolso. |
| Cabello fino | Anime de cabello al viento y fotografías; alpha suave sin erosión global. |
| Huecos internos | Logo con blanco encerrado preservado; máscaras semánticas con huecos ciertos/incertidumbre probadas por separado. |
| PNG transparente | Se detecta y conserva sin alterar. |
| Foto/fondo complejo | Dos fotografías y animal procesados; ruido sin estructura rechazado. |
| Texto fino | Tests de líneas, antialiasing y preservación de trazo. |
| Sujeto tocando borde | Una esquina ocupada y sujetos reales que llegan al borde inferior; no se rechazan solo por tocarlo. |
| Negro sobre negro / resultado incierto | Rechazo sin sustituir el original. |

Los ejemplos semánticos públicos provienen de [rembg/examples](https://github.com/danielgatis/rembg/tree/main/examples). Se usan únicamente como fixtures de QA; no se agregaron al catálogo ni se enviaron imágenes del usuario a servicios externos.

## Archivos de esta fase

| Grupo | Archivos |
| --- | --- |
| Pipeline backend | `backend/customizations/background_removal.py`, `background_errors.py`, `background_assessment.py`, `solid_background.py`, `segmentation.py`, `foreground_mask.py`, `views.py`, `management/commands/prepare_background_removal.py`, `test_hybrid_background.py` |
| Configuración | `backend/config/settings.py`, `backend/config/urls.py` (indentación), `requirements.txt` |
| Motor 3D | `frontend/static/js/customizer-3d.js`, `customizer-3d/garments.js`, `garment-model.js`, `print-surface.js`, `raycast-manager.js`, `recommendation-placement.js`, `design-manager.js`, `text-texture.js` |
| UI | `frontend/static/js/customizer.js`, `background-preview.js`, `showroom-orbit.js`, `recommendations.js`, `main.js`, `backoffice-recommendations.js`; `frontend/static/css/customizer.css`, `recommendations.css` |
| Templates | `frontend/templates/create_tshirt.html`, `components/navbar.html`, `components/hero.html` |
| QA/documentación | `tools/custom-lab/refinement-tests.cjs`, `refinement-fixtures.py`, `projection-audit.cjs`, `semantic-qa.py`, `semantic-browser-tests.cjs`, `showroom-tests.cjs`, `showroom-autoplay-tests.cjs`, `background-tests.cjs`, capturas, este informe y referencia desde `SHOWROOM.md` |

Se eliminó estado/UI obsoleto de reproducción, se unificó la lectura/validación de imágenes locales y remotas y la normal de proyección, se hicieron atómicos los cambios de diseño y se dejó explícito un fallo de recarga del orden administrativo. Los mensajes del visor ya no cubren la impresión. No se hizo un refactor general de módulos estables.

Endpoints públicos existentes conservados: `GET /api/design-recommendations/?culture=urban&garment=tshirt`, `GET /api/recommendations/cultures/`. Backoffice conserva su CRUD de culturas/recomendaciones y `POST /api/backoffice/recommendations/reorder/`. No se creó un segundo endpoint de recorte ni una segunda lógica de edición.

## Limitaciones reales

- La segmentación local en este equipo tardó **25–50 s con el modelo cargado**; una primera ejecución bajo carga tardó **116 s**. Requiere memoria/CPU y timeouts de servidor/proxy adecuados. Para tráfico concurrente conviene mover este motor a un worker con cola o equipo acelerado; eso no se desplegó en esta fase.
- No hay compatibilidad universal. Elementos ambiguos cercanos al sujeto pueden conservarse: una ilustración de prueba retuvo peces superpuestos junto al personaje. La validación no puede demostrar por sí sola que cada detalle sea correcto; por eso la confirmación visual sigue siendo obligatoria.
- La mejora de Oversize está verificada en el torso y laterales razonables. No garantiza imprimir sin distorsión sobre cuello, mangas, contorno extremo o diseños que desborden la prenda. Se conserva DecalGeometry; no se migró a UV/CanvasTexture.
- Touch/mobile se probó con Chrome emulado y CDP, no con dispositivos físicos. No se desplegó a producción ni se evaluó carga multiusuario.

