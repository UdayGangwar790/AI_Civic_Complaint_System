# Road-sign dataset cleaning report

## Scope and mapping

- Read-only source: `C:\Users\sushm\Downloads\damaged signs Hind.v1i.yolov8`
- Prepared output: `C:\Users\sushm\OneDrive\Desktop\CIVKI\ai\computer_vision\prepared_sources\road_sign_cvki`
- Deterministic seed: `20260912`
- Source class `0` is the only target positive: `damaged_missing_road_sign`.
- Source class `1` is never emitted as a positive; valid class-1-only images are negatives.
- Source labels are preserved byte-for-byte under `provenance/source_annotations/`.

## Validation

All 1339 source images were checked with Pillow (`verify()` and full pixel load), and every image/label basename pair was checked. Source label records were validated for class IDs, finite normalized coordinates in [0,1], positive detection sizes, and segmentation polygon point count/area. Valid source polygons for class 0 were converted to tight normalized detection boxes. The output contains only class-0 detection records.

### Counts

- Source images: 1339
- Eligible prepared images: 1321 (635 positive, 686 negative)
- Manual review images: 18
- Exact duplicate groups/files removed: 0/0
- Perceptual near-duplicate pairs reported (not removed): 5
- Source unchanged after processing: **True**

### Output split counts

| split | images | labels | positive images | target records | empty target labels |
|---|---:|---:|---:|---:|---:|
| train | 925 | 925 | 445 | 448 | 480 |
| val | 198 | 198 | 95 | 97 | 103 |
| test | 198 | 198 | 95 | 95 | 103 |
| manual_review | 18 | 18 | 0 | 0 | 18 |

## Conservative handling and remaining issues

Empty source labels (18) were sent to `manual_review`; they were not silently converted into negatives because image-only automation cannot establish that they are genuinely negative. Missing, malformed, unreadable, or otherwise invalid pairs would receive the same treatment (none were observed beyond empty labels). Manual-review labels are empty target files by design, while original source label bytes remain in provenance. Human review is still required for the manual-review images and for semantic correctness of automated boxes.

Exact duplicate images were removed before splitting. No exact duplicates were found in this source. A small perceptual-hash report is included for audit; near matches were not automatically discarded because perceptual similarity can be a false positive.

See `cleaning_summary.json` for machine-readable counts and `visual_qa/` for review manifests/contact sheets. No training or dataset merging was performed.
