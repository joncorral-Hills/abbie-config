---
name: parametric-3d-printing
description: >
  Parametric 3D modeling for 3D printing using CadQuery and OpenSCAD.
  Generates printable STL files from parametric specifications — dimensions,
  tolerances, and design constraints.
requires:
  bins: [python3, pip, openscad]
  pip: [cadquery, cq-editor]
---

# Parametric 3D Printing

## Overview

Generate 3D-printable STL files from parametric specifications. Use CadQuery
(Python) for programmatic modeling or OpenSCAD for declarative modeling.
Both support parametric designs — change dimensions, regenerate.

## When to Use

| Task | Tool | Why |
|------|------|-----|
| Box with lid, bracket, adapter | CadQuery | Fast, Python-native, easy iteration |
| Mechanical assembly, gears, threads | CadQuery | Boolean ops, extrusions, fillets |
| Organic shapes, complex curves | OpenSCAD | Minkowski sums, hull, smooth surfaces |
| Fractals, rule-based structures | OpenSCAD | Recursive modules, mathematical precision |
| Parametric enclosure | Either | Depends on complexity |

## CadQuery Workflow

### Basic Pattern
```python
import cadquery as cq

# Define parameters
width = 100
height = 50
depth = 30
wall_thickness = 3

# Build the model
result = (cq.Workplane("XY")
    .box(width, depth, height)
    .faces(">Z").workplane()
    .rect(width - 2*wall_thickness, depth - 2*wall_thickness)
    .cutThruAll()
)

# Export STL
cq.exporters.export(result, "enclosure.stl")
```

### Key Operations
| Operation | Method | Use |
|-----------|--------|-----|
| Box/cylinder/sphere | `.box()`, `.cylinder()`, `.sphere()` | Primitives |
| Extrude | `.extrude()` | 2D → 3D |
| Cut | `.cut()`, `.cutThruAll()` | Subtractive features |
| Fillet/chamfer | `.edges().fillet()`, `.edges().chamfer()` | Stress relief, aesthetics |
| Hole | `.hole()`, `.cboreHole()`, `.cskHole()` | Fastener holes |
| Mirror | `.mirror()` | Symmetric parts |
| Loft | `.loft()` | Transitions between profiles |
| Shell | `.faces().shell()` | Hollow parts |

### Printability Checks
Always verify:
1. **Overhangs**: Max 45° without supports (or add supports)
2. **Bridging**: Max 20mm without supports
3. **Wall thickness**: At least 2× nozzle diameter (typically 0.8mm+)
4. **Tolerances**: Holes +0.2mm, pegs -0.2mm for press fit
5. **Bed adhesion**: Flat base, avoid sharp points on bed
6. **Orientation**: Strength along layer lines — orient critical loads vertically

## OpenSCAD Workflow

### Basic Pattern
```openscad
// Parameters
width = 100;
height = 50;
depth = 30;
wall = 3;

// Main body
difference() {
    cube([width, depth, height]);
    translate([wall, wall, wall])
        cube([width - 2*wall, depth - 2*wall, height]);
}
```

### Key Modules
| Module | Use |
|--------|-----|
| `linear_extrude()` | 2D → 3D extrusion |
| `rotate_extrude()` | Lathe operations |
| `hull()` | Envelope of shapes |
| `minkowski()` | Rounding, offsets |
| `difference()`, `union()`, `intersection()` | Boolean ops |
| `for()`, `if()` | Parametric logic |
| `module` | Reusable components |

## Design Constraints for FDM Printing

| Parameter | Rule of Thumb |
|-----------|---------------|
| Min wall thickness | 0.8mm (2 perimeters @ 0.4mm nozzle) |
| Min feature size | 0.8mm (nozzle diameter) |
| Max overhang angle | 45° (no supports) |
| Max bridge length | 20mm (no supports) |
| Min hole diameter | 2mm (smaller will fuse) |
| Layer height | 0.1–0.3mm (quality vs speed) |
| Clearance for moving parts | 0.3–0.5mm |
| Press fit tolerance | -0.1 to -0.2mm |
| Loose fit tolerance | +0.2 to +0.4mm |

## File Structure

```
project/
├── design.py          # CadQuery model
├── design.scad        # OpenSCAD model (alternative)
├── params.json        # Parameter sets for different sizes
├── stl/               # Exported STL files
│   ├── v1_small.stl
│   └── v1_large.stl
└── README.md          # Print settings, orientation, notes
```

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | This file — workflow, constraints, examples |
| `templates/parametric_box.py` | Starter template for enclosures |
| `templates/parametric_bracket.py` | Starter template for brackets |
| `scripts/validate_stl.py` | Check STL for manifold, watertight, printability |
