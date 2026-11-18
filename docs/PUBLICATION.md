# Publication mapping

The recorded evidence corresponds to the ISCLS-20261108 manuscript snapshot.
Software and protocol versions are listed separately in PUBLICATION_VERSION.json.

`inputs/publication.json` maps 98 sections, 30 logical figure inputs, ten main
figures and fifteen supplementary figures. Export combines sections into 23 CSV
tables and reuses identical table data for plotting. The figure index supplies
human-readable captions; the schema and exported manifest control file lookup.

`run` computes results, exports CSVs and renders the manuscript figures in one
workflow. `report` also accepts
previously completed inputs. `report --kind publication` explicitly replays the
recorded evidence, with no downloads or model fitting. These modes never silently
substitute for each other.

Model definitions, testing families and statistical kernels are unchanged by
display compaction. The framework records source identities and validates them
during resume.
