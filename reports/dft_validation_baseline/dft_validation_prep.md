# DFT Validation: Selected Structures

**Top 20 structures selected by Ehull proxy**

| Rank | File | Formula | Ehull Proxy | MatGL Energy | SG | Atoms |
|------|------|---------|-------------|-------------|-----|-------|
| 1 | sample_36641.cif | LiFePO3 | -0.8374 | -6.5258 | P1 | 6 |
| 2 | sample_43470.cif | LiFePO4 | -0.4305 | -6.2250 | P1 | 7 |
| 3 | sample_35239.cif | LiFePO4 | -0.4272 | -6.2217 | P1 | 7 |
| 4 | sample_28179.cif | LiFePO4 | -0.4230 | -6.2175 | P1 | 7 |
| 5 | sample_8100.cif | LiFePO4 | -0.4198 | -6.2143 | P1 | 7 |
| 6 | sample_37385.cif | LiFePO4 | -0.4193 | -6.2138 | P1 | 7 |
| 7 | sample_24316.cif | LiFePO4 | -0.4160 | -6.2105 | P1 | 7 |
| 8 | sample_5273.cif | LiFePO4 | -0.4154 | -6.2099 | P1 | 7 |
| 9 | sample_6435.cif | LiFePO4 | -0.4120 | -6.2065 | P1 | 7 |
| 10 | sample_24276.cif | LiFePO4 | -0.4085 | -6.2030 | P1 | 7 |
| 11 | sample_25868.cif | LiFePO4 | -0.4079 | -6.2024 | P1 | 7 |
| 12 | sample_17524.cif | LiFePO4 | -0.4060 | -6.2005 | P1 | 7 |
| 13 | sample_25313.cif | LiFePO4 | -0.4053 | -6.1998 | P1 | 7 |
| 14 | sample_47693.cif | LiFePO4 | -0.4049 | -6.1994 | P1 | 7 |
| 15 | sample_40098.cif | LiFePO4 | -0.4044 | -6.1989 | P1 | 7 |
| 16 | sample_4640.cif | LiFePO4 | -0.4024 | -6.1969 | P1 | 7 |
| 17 | sample_19371.cif | LiFePO4 | -0.3981 | -6.1925 | P1 | 7 |
| 18 | sample_36117.cif | LiFePO4 | -0.3966 | -6.1911 | P1 | 7 |
| 19 | sample_44727.cif | LiFePO4 | -0.3945 | -6.1890 | P1 | 7 |
| 20 | sample_38303.cif | LiFePO4 | -0.3943 | -6.1888 | P1 | 7 |

## DFT Input Files

- VASP POSCAR files: `reports/dft_validation_baseline/poscar/`
- QE input files: `reports/dft_validation_baseline/qe_inputs/`
- Selected CIF files: `reports/dft_validation_baseline/selected_cifs/`

## Next Steps

1. Run VASP/QE structural relaxation for each structure
2. Record DFT energies in `dft_results_template.csv`
3. Run: `python 45_prepare_dft_validation.py analyze --proxy_csv selected_structures.csv --dft_csv dft_results.csv --out_dir reports/dft_validation_baseline`
