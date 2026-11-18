# Manuscript figures

```bash
python run.py figures --source /path/to/csv_bundle --output /path/to/new/figures
```

The source must be exported by the framework. The renderer reads all numerical
data through its manifest, including the count and tail panels. Figure numbers
follow `inputs/publication.json` and [FIGURE_INDEX.md](FIGURE_INDEX.md).

PDF is the default. Add `--tiff` for 600-dpi RGB TIFF or `--editable` for SVG/PNG.
The sole recorded evidence store is `inputs/evidence`, used only by explicit
`report --kind publication` replay and regression tests. Plotters read the
supplied exported bundle; they never silently replace computed results.
