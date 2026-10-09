# XBRL results snapshot (Part 11)

These files are a copy of `data/xbrl/`, the output of the `xbrl` DVC stage, regenerated on main and
committed so that every number in `reports/xbrl.md` can be checked without DVC or AWS access. The
pipeline itself still reads and writes `data/xbrl/`; this folder is evidence only.

Produced by (the `xbrl` stage in `dvc.yaml`):

```
python src/xbrl.py --input data/rendered/manifest.csv --output data/xbrl
python src/xbrl.py compare --path traditional --tables data/tables
python src/xbrl.py compare --path docling --tables data/docling/tables
```

| File | Contents |
|---|---|
| `facts.csv` | 1,553 numeric facts from Arelle (concept, value, unit, decimals, period, dimensions) |
| `comparison_traditional.csv`, `comparison_docling.csv` | one row per statement cell: PDF label and value, mapped concept, XBRL value, tolerance, status, mapping method, cause |
| `match_rates_*.csv` | match rate per statement |

| Path | Cells | Match | Sign | pdf_missing | Strict match rate |
|---|---:|---:|---:|---:|---:|
| traditional | 388 | 328 | 60 | 0 | 84.5% |
| docling | 388 | 325 | 60 | 3 | 83.8% |

Recompute the match rates per statement and path from these files alone:

```
python -c "import pandas as pd; [print(p, pd.read_csv(f'reports/xbrl/comparison_{p}.csv').groupby('statement').status.apply(lambda s: round((s == 'match').mean(), 4)).to_dict()) for p in ('traditional', 'docling')]"
```

`tests/test_xbrl_snapshot.py` checks in CI that this snapshot still gives the published results.
