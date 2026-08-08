"""Event-triggered simulation configuration for the CREST-AI coupling.

Trigger flow (implemented on the CREST-AI dashboard side):

 1. The hourly nowcast heatmap flags points at "flood" warning level.
 2. Flagged points are grouped by basin (HydroBASINS / EF5 facc walk);
    the simulation domain is the basin polygon's bbox at DEM resolution
    (<= 10 m 3DEP where staged), the simulation window runs from
    `spinup_hours` before t0 through the nowcast horizon.
 3. CREST-AI runs EF5/CREST for that window and exports
      - 2-D Q and SM grids at window start  -> initial conditions
      - surface + subsurface runoff grids   -> lateral-inflow forcing
 4. `run_event` integrates the shallow-water solver and writes depth /
    max-depth rasters back to the dashboard (same frame pipeline as the
    2-D hindcast maps).
"""
from __future__ import annotations

import dataclasses
import datetime


@dataclasses.dataclass
class EventConfig:
    basin_id: str                       # HydroBASINS id or gauge/vp id that triggered
    bbox: tuple                         # (w, s, e, n) lon/lat
    t_start: datetime.datetime          # includes spin-up
    t_end: datetime.datetime            # nowcast horizon
    dem_path: str                       # >=10 m DEM COG clipped to bbox
    runoff_surface: object = None       # GriddedSeriesForcing
    runoff_subsurface: object = None    # GriddedSeriesForcing
    q_init_grid: object = None          # EF5 2-D Q at t_start
    sm_init_grid: object = None         # EF5 2-D SM at t_start
    manning_path: str = None            # roughness raster (landcover-derived)
    trigger_level: str = "flood"        # nowcast warning level that fired
    output_every_s: float = 900.0       # depth-raster cadence
    device: str = "cpu"                 # "cuda" on the GPU Space


def run_event(cfg: EventConfig):
    """Placeholder for the CREST-AI wiring milestone: load DEM + Manning,
    build forcing via crestimap.forcing, integrate SWESolver, emit depth
    and max-depth rasters at cfg.output_every_s cadence."""
    raise NotImplementedError(
        "run_event lands with the CREST-AI integration milestone; "
        "see docs/DESIGN_V2.md")
