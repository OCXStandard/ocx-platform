# ocx-diagnose

Diagnoses the OCX render pipeline: checks tolerance and pipeline settings for
trimmed-NURBS panels (mesh health, chart distortion, surface deviation,
neighbour gaps/overlaps), runs tolerance sweeps and writes a self-contained
interactive plotly HTML report plus optional JSON stats.

```bash
ocx-diagnose model.3docx --panel PANEL_ID --tolerance 50 \
    --tolerance-sweep 10,25,50,100 --report out.html --json out.json --max-plates 12
```

Exit codes: 0 ok, 2 cannot parse/build the model, 3 cannot write output.
