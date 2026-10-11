
# -*- coding: utf-8 -*-
"""
Created on Tue May 12 13:03:59 2026

@author: ejones
"""

from typing import Optional, Union

import wntr
from wntr.network.model import WaterNetworkModel
from wntr.network.base import LinkStatus


def build_steady_state_from_timestep(
    inp_path: str,
    timestep_hours: Union[int, float],
    out_inp_path: Optional[str] = None,
    *,
    choose: str = "nearest_leq",
) -> WaterNetworkModel:
    """
    Run an EPANET model with WNTR, then construct a new steady-state model whose
    initial conditions match the run conditions at the requested timestep.

    Parameters
    ----------
    inp_path : str
        Path to the EPANET .inp file.
    timestep_hours : int | float
        Timestep to snapshot (in hours from simulation start).
    out_inp_path : str | None, optional
        If provided, writes the steady-state model to this .inp file.
    choose : {"exact", "nearest", "nearest_leq"}, optional
        How to select the snapshot time if the exact time is not in the results index.
        - "exact": require exact match (raises if missing)
        - "nearest": choose closest time
        - "nearest_leq": choose closest time <= target (falls back to nearest if none <=)

    Returns
    -------
    wn_ss : wntr.network.WaterNetworkModel
        New steady-state water network model.
    """
    if timestep_hours < 0:
        raise ValueError("timestep_hours must be >= 0.")

    # --- Load original model ---
    wn0 = wntr.network.WaterNetworkModel(inp_path)

    # Ensure simulation duration covers requested time (if not, extend duration)
    target_sec = int(round(float(timestep_hours) * 3600.0))
    if wn0.options.time.duration < target_sec:
        wn0.options.time.duration = target_sec

    # --- Run simulation ---
    sim = wntr.sim.EpanetSimulator(wn0)
    results = sim.run_sim()

    # Results time index is typically in seconds
    time_index = list(results.node["demand"].index)
    if len(time_index) == 0:
        raise RuntimeError("Simulation returned no timesteps in results.")

    def pick_time(tgt, times):
        if tgt in times:
            return tgt
        if choose == "exact":
            raise KeyError(f"Requested snapshot time {tgt}s not present in results index.")
        if choose == "nearest":
            return min(times, key=lambda t: abs(t - tgt))
        if choose == "nearest_leq":
            leq = [t for t in times if t <= tgt]
            if leq:
                return max(leq)
            return min(times, key=lambda t: abs(t - tgt))
        raise ValueError('choose must be one of {"exact","nearest","nearest_leq"}.')

    snap_t = pick_time(target_sec, time_index)

    # Extract run-state data at snapshot time
    node_head = results.node.get("head", None)
    node_demand = results.node.get("demand", None)
    link_status = results.link.get("status", None)      # 0/1 (Closed/Open) typically
    link_setting = results.link.get("setting", None)    # pump speed or valve setting sometimes

    if node_head is None:
        raise RuntimeError("Results missing node 'head'. Cannot set tank/reservoir conditions.")
    if node_demand is None:
        raise RuntimeError("Results missing node 'demand'. Cannot set junction demands.")

    head_t = node_head.loc[snap_t]
    demand_t = node_demand.loc[snap_t]

    status_t = link_status.loc[snap_t] if link_status is not None else None
    setting_t = link_setting.loc[snap_t] if link_setting is not None else None

    # --- Create a new model to modify (start from a fresh read to avoid side effects) ---
    wn_ss = wntr.network.WaterNetworkModel(inp_path)

    # ----------------------------
    # 1) Remove controls and rules
    # ----------------------------
    # Controls
    try:
        for cname in list(getattr(wn_ss, "control_name_list", [])):
            wn_ss.remove_control(cname)
    except Exception:
        # Older versions: controls stored differently; keep best-effort
        pass

    # Rules (if present)
    try:
        for rname in list(getattr(wn_ss, "rule_name_list", [])):
            wn_ss.remove_rule(rname)
    except Exception:
        pass

    # -------------------------------------------
    # 2) Set node conditions (tanks/reservoirs/junctions)
    # -------------------------------------------

    # Tanks: set initial level to run level at snap_t
    for tank_name, tank in wn_ss.tanks():
        if tank_name not in head_t.index:
            continue
        # Tank water level = head - elevation
        level = float(head_t[tank_name]) - float(tank.elevation)
        # Guard against tiny numerical negatives
        tank.init_level = max(level, 0.0)

        # Optional: keep within min/max if they exist (EPANET will enforce, but we clamp gently)
        try:
            tank.init_level = min(max(tank.init_level, float(tank.min_level)), float(tank.max_level))
        except Exception:
            pass

    # Reservoirs: set base head to run head at snap_t and remove head patterns
    for res_name, res in wn_ss.reservoirs():
        if res_name not in head_t.index:
            continue
        res.base_head = float(head_t[res_name])
        # Remove any head pattern
        try:
            res.head_pattern_name = None
        except Exception:
            # Some wntr versions use 'pattern' attribute
            if hasattr(res, "pattern"):
                res.pattern = None

    # Junctions: set base demand to run demand at snap_t, remove all other demands and patterns
    for junc_name, junc in wn_ss.junctions():
        if junc_name not in demand_t.index:
            continue
        run_dem = float(demand_t[junc_name])

        # EPANET/WNTR convention: demands are typically non-negative. If your model
        # uses negative demands (injections), keep as-is. Otherwise clamp small negatives.
        if run_dem < 0 and abs(run_dem) < 1e-9:
            run_dem = 0.0

        # Replace all demands with a single demand equal to run demand (no pattern)
        dlist = junc.demand_timeseries_list
        # Clear existing
        try:
            dlist.clear()
        except Exception:
            # Fallback if clear() not supported
            while len(dlist) > 0:
                dlist.pop(0)

        # Add one demand with no pattern
        dlist.append((run_dem, ''))

    # ----------------------------
    # 3) Set link initial conditions
    # ----------------------------
    # Pipes / Pumps / Valves: set initial_status to run status at snap_t
    # Pumps / Valves: also set speed/setting to run setting at snap_t when available
    def _map_status(val) -> LinkStatus:
        # EPANET status is usually 0/1; WNTR uses LinkStatus enums
        try:
            v = float(val)
        except Exception:
            # If it already looks like WNTR status, return Open as fallback
            return LinkStatus.Open
        if v <= 0.0:
            return LinkStatus.Closed 
        elif v == 2:
            return LinkStatus.Active
        else:
            return LinkStatus.Open

    for link_name, link in wn_ss.links():
        # Set status
        if status_t is not None and link_name in status_t.index:
            try:
                link.initial_status = _map_status(status_t[link_name])
            except Exception:
                # Some versions use 'status' property
                try:
                    link.status = _map_status(status_t[link_name])
                except Exception:
                    pass

        # Set setting (pump speed / valve setting) if available
        if setting_t is not None and link_name in setting_t.index:
            s = float(setting_t[link_name])

            # Pumps: speed
            if link.link_type.lower() == "pump":
                # WNTR pump has speed_timeseries (preferred) or speed
                if hasattr(link, "speed_timeseries") and link.speed_timeseries is not None:
                    # Make speed constant at snapshot
                    try:
                        link.speed_timeseries.pattern_name = None
                    except Exception:
                        pass
                    try:
                        link.speed_timeseries.base_value = s
                    except Exception:
                        pass
                elif hasattr(link, "speed"):
                    try:
                        link.speed = s
                    except Exception:
                        pass

            # Valves: setting
            elif "valve" in link.link_type.lower():
                # Remove controls/patterned behavior by making constant
                if hasattr(link, "setting"):
                    try:
                        link.setting = s
                    except Exception:
                        pass

    # -------------------------------------------
    # 4) Remove patterns, set demand multiplier = 1
    # -------------------------------------------
    wn_ss.options.hydraulic.demand_multiplier = 1.0
    wn_ss.options.hydraulic.pattern = ''

    # After removing pattern references above, remove all patterns from the model.
    # (If a pattern is still referenced somewhere, EPANET export may fail.)
    try:
        for pname in list(getattr(wn_ss, "pattern_name_list", [])):
            wn_ss.remove_pattern(pname)
    except Exception:
        pass

    # -------------------------------------------
    # 5) Set model options to steady-state
    # -------------------------------------------
    wn_ss.options.time.duration = 0
    # These are not strictly necessary, but keep them consistent/minimal:
    wn_ss.options.time.report_timestep = 0
    wn_ss.options.time.hydraulic_timestep = 0

    # -------------------------------------------
    # 6) Optionally write to inp
    # -------------------------------------------
    if out_inp_path:
        # WNTR writer
        try:
            wntr.network.io.write_inpfile(wn_ss, out_inp_path)
        except Exception:
            # Fallback writer in some WNTR versions
            inp = wntr.epanet.io.InpFile()
            inp.write(out_inp_path, wn_ss)

    return wn_ss


build_steady_state_from_timestep(
    inp_path='/Users/jonjones/Sites/UDF/flushing_journal_app/temp/updated.inp',
    timestep_hours=9,
    out_inp_path='/Users/jonjones/Sites/UDF/flushing_journal_app/temp/updatedSS.inp',
)
