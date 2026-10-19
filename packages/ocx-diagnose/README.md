# ocx-diagnose

Diagnoses the OCX render pipeline: checks tolerance and pipeline settings for
trimmed-NURBS panels (mesh health, chart distortion, surface deviation,
neighbour gaps/overlaps), runs tolerance sweeps and writes a self-contained
interactive plotly HTML report plus optional JSON stats.

```bash
ocx-diagnose diagnose model.3docx --panel PANEL_ID --tolerance 50 \
    --tolerance-sweep 10,25,50,100 --report out.html --json out.json --max-plates 12
```

Exit codes: 0 ok, 2 cannot parse/build the model, 3 cannot write output.

## TOP-001 LimitedBy diagnosis

Plot the unresolved LimitedBy contours of panels failing the OCX-TOP-001
best-practice rule (panel boundary must close):

    ocx-diagnose top-001 model.3docx [--panel ID]... [--tolerance MM] [--report out.html]

Each failing panel gets an interactive 3D figure: LimitedBy segments in
document order (coloured, sequence-labelled), ContourBounds markers
(Start ◆ / Mid ● / End ■), red dashed gap connectors annotated in mm, and
the Panel OuterContour (when present) as a grey reference curve.
Exit codes: 0 all plotted panels close, 1 at least one does not close,
2 cannot parse/build, 3 cannot write output.
