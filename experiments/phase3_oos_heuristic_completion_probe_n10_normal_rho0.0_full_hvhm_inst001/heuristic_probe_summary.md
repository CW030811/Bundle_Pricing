# Phase 3 Heuristic Completion Probe

- Instance: `cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm`
- Setup: `normal_rho0.0_full_hvhm`
- Anchor bundle count: `37`

## Baseline

- Restricted FCP OOS revenue: `2.399032`

## Heuristic Variants

| Variant | OOS Revenue | Delta vs Restricted | In-Sample Revenue | Anchor Preserved | Subadd Violations | Max Violation |
| --- | ---: | ---: | ---: | --- | ---: | ---: |
| `same_size_anchor_max` | -6.154703 | -8.553735 | -6.348649 | `True` | `8509` | `16.481879` |
| `bsp_clipped_to_anchor_range` | -6.154703 | -8.553735 | -6.348649 | `True` | `8509` | `16.313542` |
| `same_size_anchor_upper_bound` | -6.154703 | -8.553735 | -6.348649 | `True` | `8509` | `16.481879` |
| `same_size_anchor_mean` | -7.098421 | -9.497453 | -7.241658 | `True` | `15415` | `14.272584` |
| `same_size_anchor_median` | -7.125485 | -9.524517 | -7.241658 | `True` | `11941` | `14.272584` |
| `same_size_anchor_min` | -11.998587 | -14.397619 | -12.032905 | `True` | `16519` | `16.481879` |
| `same_size_anchor_lower_bound` | -11.998587 | -14.397619 | -12.032905 | `True` | `16519` | `16.481879` |

