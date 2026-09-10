# Custom Lab: availability and Hoodie

The active catalog uses Remera Clásica, Remera Oversize and Hoodie. The second old test product is archived rather than merged: its price and inventory differ, and its historical references remain intact. New products and variants start at zero price/stock where no commercial value was provided.

Stock is physical inventory available for allocation, not permission to design or order. Active variants at zero stock remain selectable. Product/variant ownership, active flags, quantity, configuration and asset checks remain enforced.

OrderItem.quantity is the requested quantity. allocated_quantity records physical units consumed. shortage_quantity is calculated, never stored separately. Historical items are migrated as fully allocated because the old checkout required full stock. Cancelled orders retain the historical allocation but are not eligible for further allocation.

orders.services.allocate_variant_stock locks each variant and allocates pending/confirmed order items FIFO by order creation and item ID. RESTOCK and increasing SET operations call it transactionally. It writes ORDER movements (the existing equivalent of ORDER_ALLOCATION), with an order FK. Allocation changes no payment or order status. Production transitions require complete allocation. Cancellation restores allocated units only, once. Database constraints prohibit negative physical stock and allocation beyond the requested quantity.

Backoffice shows requested, assigned, missing and free physical stock separately. The order list filters by AVAILABLE or AWAITING_STOCK. Stock adjustments explain FIFO allocation before submission. Prices remain editable in the existing product form.

## Hoodie asset

Rebuild from the repository root:

    node tools/custom-lab/convert-hoodie.mjs

Uses the existing local Three.js r160 FBXLoader / GLTFExporter and gltf-validator. No external converter is required. See hoodie-inspection.json for source hash, UV bounds, mesh counts and validation output (zero errors and warnings).

Low_Hoodie.fbx contains Base (13,164 triangles), Hood_on (2,028), Hood_off (2,028). Each has position, normal and UV attributes. There are no texture maps or morph targets. Its original material type is unknown to FBXLoader, so conversion explicitly replaces all slots with plain MeshStandardMaterial. Geometry and UVs are preserved. The model is normalized to one unit high, Y up and front +Z; both hood alternatives are exported.

GARMENTS.hoodie maps down/up to Hood_off/Hood_on. Visibility changes retain the scene, renderer, controls, material and design resources. Designs record their surface mesh; designs on the hidden hood are retained and reappear with that hood. Missing hoodState defaults to down. Previews and persisted configurations use the same mechanism as the other garments.

Browser verification (start Django on 127.0.0.1:8765 first):

    node tools/custom-lab/commerce-tests.cjs
    node tools/custom-lab/browser-tests.cjs

The commerce test supplies a zero-stock catalog and intercepts writes; it checks all three garments, text, images, transformations, previews, restoration, cart payloads and both hood states. The image exported into products/assets/hoodie.webp is a plain render of the supplied model.
