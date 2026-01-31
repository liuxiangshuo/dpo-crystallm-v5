## NaCl: baseline vs DPO vs trimmed-DPO (MatGL proxy energy per atom)
Lower (more negative) is better.

| metric | baseline | DPO | DPO (trimmed pairs) |
|---|---:|---:|---:|
| n | 200 | 200 | 200 |
| min | -3.31083 | -3.31078 | -3.31043 |
| p10 | -3.30855 | -3.30847 | -3.30835 |
| median | -3.23071 | -3.30463 | -3.30469 |
| mean | -3.24149 | -3.25621 | -3.26427 |
| p90 | -3.22555 | -3.20431 | -3.20439 |
| max | -2.37677 | -1.90403 | -2.06425 |

**Takeaway:** trimming extreme rejected outliers keeps the median/mean gains while substantially improving the worst-case tail.
