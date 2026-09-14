# CVKI M1.10 — Waterlogging Augmentation Policy

- **Project**: Civic Vision & Knowledge Intelligence (CVKI)
- **Module**: M1.10 — Waterlogging Dataset Improvement & Preparation
- **Document**: Evidence-Based Data Augmentation Policy & Hyperparameter Specification
- **Status**: **REVIEW / PROPOSAL** (Planning only — no model training)
- **Date**: 2026-09-12

---

## 1. Physical Constraints & Empirical Rationale

Object detection models trained on isotropic objects (such as circular manholes or generic particles) can tolerate omnidirectional rotation augmentations. However, **road waterlogging is strictly constrained by gravitational physics and planar geometry**:

1. **Gravity Plane**: Water pools form horizontal, equipotential surfaces parallel to the Earth's geoid. In camera perspective, road surfaces slope toward a vanishing horizon line located in the upper third of the frame.
2. **Specular Sky Reflection**: Puddle luminance gradients rely on downward sky reflection and Fresnel reflection angles. Rotating an image 90° or 180° places bright sky reflections on the bottom or side, contradicting physical optics.
3. **M1.9 Failure Evidence**:
   - In the Roboflow source dataset, 90° and 270° rotations caused horizontal roads to appear vertical.
   - The Phase C audit discovered **42 images with artificial vertical rotations** and **84 narrow stripe annotations** (19.1% of all boxes) oriented like vertical walls of water.
   - The baseline YOLOv8n detector learned false spatial priors, generating 18 false positives on shadows and missing 27 ground-truth puddles.

Therefore, the augmentation policy for road waterlogging must strictly preserve natural gravity vectors and perspective horizons.

---

## 2. Allowed Transformations (Physically Realistic)

The following transformations are permitted for YOLOv8 training because they model real-world environmental and sensor variations without violating gravitational physics:

| Transformation | Recommended Hyperparameter | Physical Rationale & Boundary Constraints |
|---|---|---|
| **Horizontal Flip** | `fliplr: 0.5` | Physically valid. Mirroring a roadway horizontally preserves the level ground plane, horizontal puddle pooling, and driver perspective while simulating left-hand vs. right-hand drive traffic flow. |
| **Brightness & Contrast (Photometric Jitter)** | `hsv_h: 0.015`<br>`hsv_s: 0.40`<br>`hsv_v: 0.30` | Models real-world illumination shifts: sudden cloud cover, bright midday direct sun, twilight, and variable asphalt dampness without altering spatial coordinates. |
| **Mild Scale Jitter** | `scale: 0.15` ($\pm 15\%$) | Simulates varying camera focal lengths, sensor zoom, and distance to puddle (10m vs 30m ahead). Bounding boxes scaled proportionally. |
| **Mild Translation / Shift** | `translate: 0.08` ($\pm 8\%$) | Simulates vehicle lane positioning changes (driving in center lane vs curb lane) without cropping out primary puddle hazards. |
| **Mild Perspective Distortion** | `perspective: 0.0005` | Simulates slight variations in camera pitch/roll mounting angle on vehicle windshields ($\pm 3^\circ$). Constrained to prevent road curvature warping. |
| **Mild Gaussian Blur / Sensor Noise** | Optional preprocessing (`blur: 0.01`) | Simulates windshield rain droplets or low-cost dashcam sensor noise in wet weather. |

---

## 3. Strictly Prohibited Transformations (Banned)

The following transformations are **strictly forbidden** during data preparation and model training:

| Prohibited Transformation | Default YOLO Parameter | Mandated Setting | Justification & Failure Mechanism |
|---|---|---|---|
| **90°, 180°, 270° Orthogonal Rotations** | `degrees: 0.0` (or `rot90`) | **`degrees: 0.0` (STRICT ZERO)** | Rotates the ground plane 90° sideways, turning horizontal puddles into vertical walls of water and destroying sky reflection physics. Identified in M1.9 as a major contributor to baseline failure. |
| **Vertical Flip (Inversion)** | `flipud: 0.0` | **`flipud: 0.0` (STRICT ZERO)** | Flips the ground plane upside down, placing asphalt puddles in the sky and clouds on the ground. Totally destroys gravitational scene priors. |
| **Random Continuous Rotation** | `degrees: > 0.0` | **`degrees: 0.0` (DISABLED)** | Even mild continuous tilts ($> 5^\circ$) cause bounding box dilation and enclose non-water background road shoulders. |
| **Arbitrary Multi-Quadrant Mosaic** | `mosaic: 1.0` (YOLO default) | **`mosaic: 0.0` or isolated** | The original dataset's 2x2 collages caused extreme box fragmentation (4–10 boxes/image) and edge slicing. For improved training, mosaic should either be disabled (`mosaic: 0.0`) or constrained to single-scene crops. |
| **Extreme Shear** | `shear: 0.0` | **`shear: 0.0` (STRICT ZERO)** | Shearing distorts the planar geometry of the road surface, skewing rectangular lane markings and rectangular puddle boundaries. |
| **Cutout / Extreme Erasing** | `erasing: 0.0` | **`erasing: 0.0` (DISABLED)** | Randomly masking rectangular patches creates artificial dark rectangles on the road that look identical to oil stains or asphalt patches, promoting false positives. |

---

## 4. Training Configuration Specification (`hyp.improved.yaml`)

For any future retrainings following M1.10 approval, the augmentation parameters in Ultralytics YOLOv8 must be explicitly constrained in an isolated training configuration:

```yaml
# CIVKI M1.10 - Gravity-Constrained Civic Augmentation Hyperparameters
# Path: ai/computer_vision/training/configs/hyp.improved_civic.yaml

# Photometric Augmentations (Safe)
hsv_h: 0.015    # Subtle hue variation (leaves road tint realistic)
hsv_s: 0.400    # Saturation variation (damp vs dry asphalt contrast)
hsv_v: 0.300    # Brightness variation (cloud shadows, sunbreaks)

# Spatial & Geometric Augmentations (Physically Constrained)
degrees: 0.0    # STRICTLY ZERO: No in-plane rotation
translate: 0.08 # Mild translation (+- 8%)
scale: 0.15     # Mild scale (+- 15%)
shear: 0.0      # STRICTLY ZERO: No perspective shearing
perspective: 0.0005 # Minimal perspective jitter
flipud: 0.0     # STRICTLY ZERO: No upside-down vertical flips
fliplr: 0.5     # ALLOWED: Horizontal symmetry is physically valid
bgr: 0.0        # No artificial channel swaps

# Compositional Augmentations
mosaic: 0.0     # ZERO: Prevents artificial 4-image collage artifacts
mixup: 0.0      # ZERO: Blending two scenes creates ghostly non-physical water
copy_paste: 0.0 # ZERO: Pasting water onto dry pavement creates jagged boundary artifacts
```

---

## 5. Verification & Compliance Monitoring

Before any future training run begins, automated sanity checks in `scripts/verify_augmentations.py` must verify:
1. `data.yaml` and model training arguments enforce `degrees == 0.0`, `flipud == 0.0`, `mosaic == 0.0`.
2. Random batch visualization inspects the first 3 training batches (`train_batch0.jpg`, `train_batch1.jpg`, `train_batch2.jpg`) to visually confirm that all water surfaces remain strictly horizontal.
