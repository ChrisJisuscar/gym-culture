# Backoffice comercial

## Auditoría y causas

- Stock usa `ProductVariant.stock`; no existe un modelo Stock separado. `stock_queryset()` ya incluía stock cero y productos inactivos. La base local tenía 93 variantes, 32 de Hoodie. La página de 20 filas ordenadas por nombre mostraba exclusivamente Hoodies. Se amplió la página a 100, conservando paginación y filtros del servidor.
- Los IDs y snapshots del pedido Oversize local eran correctos. No se reprodujo un Oversize vinculado a Hoodie. Se encontró el snapshot antiguo `Hoodie2` en un producto actualmente llamado Hoodie. No se reescribieron snapshots ni relaciones históricas. Las etiquetas visibles se resuelven con `variant.product`, o `product` si no hay variante; el nombre original queda expuesto como `product_name_snapshot`.
- Custom Lab actual valida prenda/producto/variante. El carrito legacy no comparaba la prenda del diseño con el producto: se agregó esa validación tanto al ingreso como en checkout, incluso para carritos ya guardados.

## Inventario

Agregar y retirar usan el servicio transaccional existente, bloqueo de variante y StockMovement. Un retiro inválido no modifica inventario ni genera movimientos. Una reposición asigna FIFO a pedidos PENDING/CONFIRMED y la UI vuelve a consultar inventario e historial.

Se eliminó **Establecer** de Stock y se rechaza SET en su endpoint de ajustes. Se conserva el tipo interno SET para stock inicial y conciliación por conteo físico desde la ficha de producto: esa ficha ya recibe cantidades absolutas y registra usuario, motivo, antes/después y fecha. Es una corrección administrativa auditada, no una tercera operación cotidiana. Los movimientos SET históricos se conservan.

## Archivado

PATCH del detalle de pedido acepta únicamente un booleano `is_archived`. Registra fecha/administrador y es idempotente. Los listados administrativos y producción ocultan archivados; `?archived=true` permite consultarlos. Restaurar permite volver a gestionar su estado. No hay borrado físico.

Archivar cambia visibilidad, no cancela ni devuelve unidades. Sus reservas y faltantes siguen participando en inventario/FIFO. Para liberar unidades debe cancelarse primero mediante el flujo existente, cuando el estado lo permite. La confirmación lo explica. Pagos, assets, snapshots y referencias permanecen intactos; el cliente conserva acceso a su historial.

Clientes reutiliza `is_active`; desactivar impide autenticación y conserva todos los pedidos. `?active=false` muestra desactivados. Se excluyen cuentas staff/superuser de estas acciones. ADMIN/is_staff se exige en backend, con confirmación en UI para archivar, restaurar, desactivar y reactivar.

Migración: `orders/0005_order_archived_at_order_archived_by_and_more.py`, aplicada localmente. No requiere migración de clientes ni de catálogo.

## Dashboard

Un request a `/api/backoffice/dashboard/?period=7|30|12m` entrega ocho KPIs, ciudades, períodos, estados, productos, inventario crítico y pedidos recientes.

- Ventas = suma de `Order.total` para payment_status PAID y estado distinto de CANCELLED. Ticket = promedio de esos mismos pedidos. Incluyen envío e historial archivado; excluyen pendientes, reembolsados y parcialmente reembolsados. Son ventas brutas de pedidos pagados, no conciliación contable ni flujo neto de caja. Múltiples intentos de pago no multiplican importes.
- Pedidos totales y ciudades incluyen todo el historial; ciudades usan shipping_city normalizada por mayúsculas/espacios, sin inferir otra ciudad ni corregir direcciones de clientes.
- Pendientes, producción y estados usan pedidos no archivados. Clientes cuenta clientes activos sin staff.
- Top productos suma cantidades por Product real y excluye cancelados. Stock crítico incluye stock cero, hasta LOW_STOCK_THRESHOLD y faltantes, con hasta 20 variantes ordenadas por urgencia.
- Períodos se agrupan por creación del pedido en America/Asuncion. Días/meses sin actividad llevan cero observado; nunca se generan ventas o pedidos ficticios.

Chart.js 4.5.1 se sirve localmente en `frontend/static/vendor/chartjs/`, con licencia MIT. Integración vanilla documentada en https://www.chartjs.org/docs/latest/getting-started/integration.html. No usa CDN en ejecución ni React. Empty states, alternativa textual accesible, counters y transiciones respetan reduced motion.

## Archivos y comprobación

Backend: modelos/serializers/services/views de orders, nuevo orders/dashboard.py; serializers/views de products y users; validación legacy en cart/serializers.py. Frontend: templates de backoffice, backoffice.js, backoffice.css y vendor Chart.js.

Tests: orders/test_backoffice.py, products/tests.py y tools/custom-lab/backoffice-tests.cjs. Ejecutar Django desde backend para que descubra la suite: `python manage.py check`, `python manage.py test --noinput`, `python manage.py makemigrations --check --dry-run`; luego `git diff --check`.

El browser test consulta páginas/endpoints reales. Intercepta solamente mutaciones de stock y archivado/desactivación para probar confirmaciones y refresh sin alterar datos comerciales locales; las mutaciones reales se verifican en la base de tests Django.

Resultados locales (2026-09-10): suite completa, 180 tests aprobados; después del último caso legacy y la simplificación del cálculo de períodos, regresión de cart + orders.test_backoffice, 40 tests aprobados. `check`, `makemigrations --check --dry-run`, `git diff --check` y sintaxis JavaScript: sin errores. Browser: seis pantallas reales, detalles, filtros de stock, períodos, confirmaciones, reposición con refresh y cuatro pantallas móviles con reduced motion; sin errores JS ni desbordamiento horizontal. Capturas en `.venv/backoffice-audit/` (ignoradas por git).
