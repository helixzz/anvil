# Comparing devices

The **Compare** page lets you put multiple device models side-by-side
for the same phase.

## Pick models

The model picker shows every distinct model that has at least one
completed run. Click to toggle selection.

## Pick the common phase

Anvil computes the intersection of phase names across your selected
models and offers those for comparison. If two models ran different
profiles with no overlapping phase, Compare reports no common phases.

## Pick the metric

Currently:

- `read_iops`, `write_iops`
- `read_bw_bytes`, `write_bw_bytes`
- `read_clat_mean_ns`, `read_clat_p99_ns`

## Read the chart

Two overlays:

- **Bar**: mean of each model's run-sample values for the selected
  metric in the selected phase
- **Scatter**: every individual run's value so you can see the
  spread, outliers, and sample count

Hover any bar for the mean ± stdev; hover any scatter point for the
specific run and its timestamp.

## Share the view

The **Share view** button copies the current URL. The URL carries
the full view state as query parameters (`models=`, `phase=`,
`metric=`), so anyone on the same Anvil instance who opens it lands
on the exact same comparison.

For a **public** share that works without login, use the Saved
Comparisons feature — see [sharing](sharing.md).
