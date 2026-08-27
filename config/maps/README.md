# Nav2 map input

Phase B requires the validated map files supplied by the operator. Install them
here as:

```text
j100_0519.yaml
<image file referenced by j100_0519.yaml>
```

Do not create a placeholder occupancy map. `launch_nav2:=true` must remain off
until both files exist and have been checked in RViz.
