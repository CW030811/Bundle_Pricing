# BSP vs FCP Detailed Choice Analysis

## Instance

- instance: `cpbsd_instance_001_N10_K50_normal_rho0.0_full_hvhm.msgpack`
- setup: `{'n_products': 10, 'k_samples': 50, 'dist_family': 'normal', 'rho': 0.0, 'heterogeneity': 'full', 'cost_scenario': 'hvhm', 'seed': 20260321}`
- BSP offered sizes: `[0, 2, 3, 4, 5, 6, 7, 8, 9, 10]`
- FCP priced bundles: `37` over restricted assortment size `37`
- FCP size support: `[0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10]`

## In Sample

- customer count: `50`
- BSP avg profit: `2.878430`
- FCP avg profit: `3.561872`
- BSP purchase count: `44`
- FCP purchase count: `47`
- BSP purchase but FCP no-purchase: `0`
- BSP chosen exact bundle not in FCP menu: `11`
- Same bundle count: `11`
- Same size count: `14`
- BSP profit > FCP profit count: `9`
- FCP profit > BSP profit count: `38`

## Oos

- customer count: `5000`
- BSP avg profit: `2.450536`
- FCP avg profit: `2.399032`
- BSP purchase count: `3790`
- FCP purchase count: `3456`
- BSP purchase but FCP no-purchase: `533`
- BSP chosen exact bundle not in FCP menu: `1186`
- Same bundle count: `1503`
- Same size count: `1763`
- BSP profit > FCP profit count: `1405`
- FCP profit > BSP profit count: `2584`

## Files

- [customer_comparison_in_sample.csv](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/instance001_bsp_fcp_compare/customer_comparison_in_sample.csv)
- [customer_comparison_oos.csv](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/instance001_bsp_fcp_compare/customer_comparison_oos.csv)
- [summary.json](/Users/sensen/.openclaw/workspace/domains/revenue-management/research-tracker/weekly-reports/2026-W16-fcp-gcn-vs-cpbsd-main-n5/instance001_bsp_fcp_compare/summary.json)
