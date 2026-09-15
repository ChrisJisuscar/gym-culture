"""Conservative solid-background removal, using only edge-connected pixels.

No subject segmentation or model inference: ambiguous images are refused. The
original upload is never modified or stored by this service.
"""
import io

import numpy as np
from PIL import Image
from scipy import ndimage

from .background_errors import BackgroundRemovalRejected


def rgb_to_lab(rgb):
    """sRGB -> CIE Lab D65; delta E 76 is sufficient for near-solid colors."""
    rgb = np.asarray(rgb, dtype=np.float32) / 255.0
    linear = np.where(rgb <= .04045, rgb / 12.92, ((rgb + .055) / 1.055) ** 2.4)
    xyz = linear @ np.array([[.4124564, .2126729, .0193339], [.3575761, .7151522, .1191920], [.1804375, .0721750, .9503041]], dtype=np.float32)
    xyz /= np.array([.95047, 1, 1.08883], dtype=np.float32)
    f = np.where(xyz > .008856, np.cbrt(xyz), xyz * 7.787 + 16 / 116)
    return np.stack((116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])), axis=-1)


class SolidBackgroundRemover:
    def estimate_background(self, image, compressed):
        sample = image.convert('RGB')
        sample.thumbnail((512, 512), Image.Resampling.BOX)
        colors = np.asarray(sample)
        band = max(1, round(min(sample.size) * .012))
        sides = [colors[:band].reshape(-1, 3), colors[-band:].reshape(-1, 3), colors[:, :band].reshape(-1, 3), colors[:, -band:].reshape(-1, 3)]
        border = np.concatenate(sides)
        border_lab = rgb_to_lab(border)
        noise = float(np.median(np.concatenate([np.linalg.norm(np.diff(rgb_to_lab(side), axis=0), axis=1) for side in sides])))
        if noise > 14:
            raise BackgroundRemovalRejected('unstructured_noise')
        patch = max(2, round(min(sample.size) * .045))
        corners = np.array([np.median(colors[y, x].reshape(-1, 3), axis=0) for y in (slice(0, patch), slice(-patch, None)) for x in (slice(0, patch), slice(-patch, None))])
        remaining = np.ones(len(border), dtype=bool)
        backgrounds, tolerances, variations = [], [], []
        radius = min(10, 6 + noise * .6)
        for _ in range(3):
            if remaining.mean() < .08:
                break
            bins, counts = np.unique(border[remaining] // 16, axis=0, return_counts=True)
            cluster = border[remaining & np.all(border // 16 == bins[counts.argmax()], axis=1)]
            color = np.median(cluster, axis=0)
            distance = np.linalg.norm(border_lab - rgb_to_lab(color), axis=1)
            members = remaining & (distance <= radius)
            if members.mean() < .08:
                break
            remaining[members] = False
            color = np.median(border[members], axis=0)
            if backgrounds and np.linalg.norm(rgb_to_lab(color) - rgb_to_lab(backgrounds[0])) > 14:
                continue  # Unrelated border colors are likely ink, not JPEG variation.
            variation = float(np.quantile(np.linalg.norm(border_lab[members] - rgb_to_lab(color), axis=1), .9))
            tolerance = float(np.clip(variation * 1.35 + 2 + (1 if compressed else 0) + (.5 if min(image.size) < 160 else 0), 4 if compressed else 2.5, 10))
            backgrounds.append(color); tolerances.append(tolerance); variations.append(variation)
        if not backgrounds:
            raise BackgroundRemovalRejected('no_background_cluster')
        backgrounds = np.array(backgrounds, dtype=np.float32)
        matched = np.any(np.linalg.norm(border_lab[:, None] - rgb_to_lab(backgrounds), axis=2) <= np.array(tolerances), axis=1)
        coverage = float(matched.mean())
        corner_coverage = float(np.any(np.linalg.norm(rgb_to_lab(corners)[:, None] - rgb_to_lab(backgrounds), axis=2) <= np.array(tolerances), axis=1).mean())
        side_coverage = [np.any(np.linalg.norm(rgb_to_lab(side)[:, None] - rgb_to_lab(backgrounds), axis=2) <= np.array(tolerances), axis=1).mean() for side in sides]
        if coverage < .42 or corner_coverage < .5 or sum(value >= .3 for value in side_coverage) < 2:
            raise BackgroundRemovalRejected('no_reliable_exterior', coverage)
        return backgrounds, np.array(tolerances), coverage, corner_coverage, max(variations), noise

    def segment(self, rgb, backgrounds, tolerances):
        # Chunk conversion bounds memory while retaining the original resolution.
        shape = rgb.shape[:2]
        distance = np.full(shape, np.inf, dtype=np.float32)
        nearest = np.zeros(shape, dtype=np.uint8)
        candidates = np.zeros(shape, dtype=bool)
        for y in range(0, shape[0], 256):
            lab = rgb_to_lab(rgb[y:y + 256])
            for index, color in enumerate(backgrounds):
                delta = np.linalg.norm(lab - rgb_to_lab(color), axis=2)
                closer = delta < distance[y:y + 256]
                distance[y:y + 256][closer] = delta[closer]
                nearest[y:y + 256][closer] = index
                candidates[y:y + 256] |= delta <= tolerances[index]
        # Closing repairs isolated one-pixel compression gaps in a contour. It
        # only protects extra pixels; it never erodes the original foreground.
        barrier = ~candidates
        repaired = barrier | ndimage.binary_closing(barrier, structure=np.ones((3, 3), dtype=bool))
        protected = ndimage.binary_fill_holes(repaired)
        candidates &= ~protected
        seeds = np.zeros(shape, dtype=bool)
        seeds[0] = candidates[0]; seeds[-1] = candidates[-1]
        seeds[:, 0] = candidates[:, 0]; seeds[:, -1] = candidates[:, -1]
        connected = ndimage.binary_propagation(seeds, mask=candidates)
        removed = float(connected.mean())
        distinct = distance[barrier]
        contrast = float(np.quantile(distinct, .75)) if distinct.size else 0
        if removed < .025 or distinct.size < max(8, distance.size * .0005):
            raise BackgroundRemovalRejected('no_clear_foreground')
        if contrast < max(14, float(max(tolerances)) * 1.6):
            raise BackgroundRemovalRejected('low_subject_contrast')
        return distance, nearest, connected, removed, contrast

    def remove_image(self, image, compressed=False):
        original = image.copy()
        rgb = np.asarray(original)[..., :3]
        backgrounds, tolerances, coverage, corners, variation, noise = self.estimate_background(original, compressed)
        fallback = False
        try:
            distance, nearest_background, connected, removed_fraction, contrast = self.segment(rgb, backgrounds, tolerances)
        except BackgroundRemovalRejected:
            # A tighter connected mask can keep weak contours that the
            # adaptive attempt could not separate with enough confidence.
            fallback = True
            tolerances = np.minimum(tolerances, 3)
            distance, nearest_background, connected, removed_fraction, contrast = self.segment(rgb, backgrounds, tolerances)
        confidence = .35 * coverage + .15 * corners + .2 * max(0, 1 - variation / 14) + .3 * min(1, contrast / 40)
        self.background_confidence = confidence
        self.confidence_level = 'LOW' if fallback or confidence < .65 or contrast < 25 else 'HIGH' if confidence >= .85 and coverage >= .88 and variation < 4 else 'MEDIUM'
        tolerance = float(max(tolerances))
        self.tolerance = tolerance
        self.removed_fraction = removed_fraction
        alpha = np.full(connected.shape, 255, dtype=np.uint8)
        alpha[connected] = 0
        # Feather only one pixel on the removed side. Retained strokes and
        # enclosed areas (even if exactly background-colored) stay intact.
        fringe = connected & ndimage.binary_dilation(~connected) & (distance > tolerance * .6)
        alpha[fringe] = np.clip((distance[fringe] / tolerance - .6) * 320, 0, 128).astype(np.uint8)
        # Remove the old matte from a single external antialiased pixel row.
        # Interior holes are never candidates. Only nearly-background colors
        # consistent with a nearby contrasting pixel receive partial alpha;
        # solid strokes are untouched, and no erosion is performed.
        outer_edge = ~connected & ndimage.binary_dilation(connected) & (distance < 18)
        if outer_edge.any():
            strong = distance >= max(25, tolerance * 4)
            proximity, nearest = ndimage.distance_transform_edt(~strong, return_indices=True)
            edge = outer_edge & (proximity <= 3)
            current = rgb[edge].astype(np.float32)
            foreground = rgb[nearest[0][edge], nearest[1][edge]].astype(np.float32)
            background = backgrounds[nearest_background[edge]]
            vector = foreground - background
            opacity = np.clip(np.sum((current - background) * vector, axis=1) / np.maximum(np.sum(vector * vector, axis=1), 1), .01, 1)
            residual = np.linalg.norm(current - (background + opacity[:, None] * vector), axis=1)
            safe = (residual < 6) & (opacity < .5)
            refined = np.array(original)
            pixels = refined[edge]
            pixels[safe, :3] = np.clip((current[safe] - (1 - opacity[safe, None]) * background[safe]) / opacity[safe, None], 0, 255).astype(np.uint8)
            refined[edge] = pixels
            edge_alpha = alpha[edge]
            edge_alpha[safe] = np.round(opacity[safe] * 255).astype(np.uint8)
            alpha[edge] = edge_alpha
            original = Image.fromarray(refined)
        original.putalpha(Image.fromarray(alpha))
        output = io.BytesIO()
        original.save(output, 'PNG', optimize=True)
        return output.getvalue()
