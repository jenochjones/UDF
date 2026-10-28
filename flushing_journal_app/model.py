
from copyreg import pickle
import math
import os
import re
from collections import deque

from typing import Callable, Optional, Union

import wntr
from wntr.network.model import WaterNetworkModel
from wntr.network.base import LinkStatus

from constants import (
    CUBIC_METERS_PER_SECOND_TO_GALLONS_PER_MINUTE,
    CUBIC_METERS_TO_GALLONS,
    DEFAULT_MAX_FLUSH_DIAMETER_IN,
    DEFAULT_MAX_FLUSH_LENGTH_FT,
    DEFAULT_MAX_FLUSH_VELOCITY_FPS,
    DEFAULT_MIN_FLUSH_VELOCITY_FPS,
    DEFAULT_MIN_RESIDUAL_PRESSURE_PSI,
    DEFAULT_ORIFICE_DIAMETER_IN,
    DEFAULT_PIPES_TO_REFLUSH,
    DEFAULT_START_TO_FLUSH_VELOCITY_RATIO,
    DEFAULT_VOLUME_TURNOVERS,
    METERS_TO_FEET,
    METERS_TO_INCHES,
    ORIFICE_EMITTER_COEFFICIENT_DENOMINATOR,
    ORIFICE_EMITTER_COEFFICIENT_NUMERATOR,
    PSI_PER_FOOT_OF_WATER,
)



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
        if link.link_type.lower() == "valve":
            continue
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

            ## Valves: setting
            #elif "valve" in link.link_type.lower():
            #    # Remove controls/patterned behavior by making constant
            #    if hasattr(link, "setting"):
            #        try:
            #            link.setting = s
            #        except Exception:
            #            pass

    # -------------------------------------------
    # 4) Remove patterns, set demand multiplier = 1
    # -------------------------------------------
    wn_ss.options.hydraulic.demand_multiplier = 1.0
    wn_ss.options.hydraulic.pattern = None

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


def run_water_network_model(
    model_store: dict,
    sequences: list,
    options: Optional[dict] = None,
    progress_callback: Optional[Callable[[int, str], None]] = None,
) -> dict:
    """
    Run the water network model using the provided model store.

    Args:
        model_store (dict): A dictionary containing the water network model and other relevant data.
        sequences (list): A list of sequences to be processed.
        options (dict | None): Flushing settings used for this run.
        progress_callback: Optional callback receiving progress percentage and text.

    Returns:
        dict: Results for each sequence and operation.
    """

    inp_file = model_store.get("inp_path")
    if not inp_file:
        raise ValueError("No base water network model is available to run.")
    model_dir = model_store.get("model_dir") or os.path.dirname(inp_file) or os.getcwd()
    os.makedirs(model_dir, exist_ok=True)

    mapping = model_store.get("element_mapping", {})
    generated_inp_files = model_store.setdefault("generated_inp_files", [])
    run_options = dict(model_store.get("flush_options", {}))
    if options is not None:
        if not isinstance(options, dict):
            raise ValueError("Flushing options must be an object.")
        run_options.update(options)

    def numeric_option(name, default, *, allow_zero=False):
        try:
            value = float(run_options.get(name, default))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Flushing option '{name}' must be numeric.") from exc
        if not math.isfinite(value) or value < 0 or (value == 0 and not allow_zero):
            qualifier = "non-negative" if allow_zero else "greater than zero"
            raise ValueError(f"Flushing option '{name}' must be {qualifier}.")
        return value

    velocity_multiplier = numeric_option(
        "start_vel_to_flushing_vel_ratio",
        DEFAULT_START_TO_FLUSH_VELOCITY_RATIO,
    )
    minimum_flush_velocity_fps = numeric_option(
        "min_flush_vel", DEFAULT_MIN_FLUSH_VELOCITY_FPS
    )
    volume_turnovers = numeric_option(
        "volume_turnovers", DEFAULT_VOLUME_TURNOVERS
    )
    default_orifice_diam = numeric_option(
        "default_orifice_diam", DEFAULT_ORIFICE_DIAMETER_IN
    )
    max_flush_length = numeric_option(
        "max_flush_length", DEFAULT_MAX_FLUSH_LENGTH_FT, allow_zero=True
    )
    max_flush_diam = numeric_option(
        "max_flush_diam", DEFAULT_MAX_FLUSH_DIAMETER_IN, allow_zero=True
    )
    max_flush_vel = numeric_option(
        "max_flush_vel", DEFAULT_MAX_FLUSH_VELOCITY_FPS, allow_zero=True
    )
    min_res_pres = numeric_option(
        "min_res_pres", DEFAULT_MIN_RESIDUAL_PRESSURE_PSI, allow_zero=True
    )
    #pres_drop_warning_limit = numeric_option(
    #    "pres_drop_warning_limit", 10.0, allow_zero=True
    #)
    try:
        pipes_to_reflush_value = float(
            run_options.get("pipes_to_reflush", DEFAULT_PIPES_TO_REFLUSH)
        )
    except (TypeError, ValueError) as exc:
        raise ValueError("Flushing option 'pipes_to_reflush' must be an integer.") from exc
    if (
        not math.isfinite(pipes_to_reflush_value)
        or pipes_to_reflush_value < 0
        or not pipes_to_reflush_value.is_integer()
    ):
        raise ValueError(
            "Flushing option 'pipes_to_reflush' must be a non-negative integer."
        )
    pipes_to_reflush = int(pipes_to_reflush_value)
    run_options.update(
        {
            "start_vel_to_flushing_vel_ratio": velocity_multiplier,
            "min_flush_vel": minimum_flush_velocity_fps,
            "volume_turnovers": volume_turnovers,
            "default_orifice_diam": default_orifice_diam,
            "max_flush_length": max_flush_length,
            "max_flush_diam": max_flush_diam,
            "max_flush_vel": max_flush_vel,
            "min_res_pres": min_res_pres,
            #"pres_drop_warning_limit": pres_drop_warning_limit,
            "pipes_to_reflush": pipes_to_reflush,
        }
    )
    model_store["flush_options"] = run_options

    def _filename_part(value):
        return (
            re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value)).strip("._")[:100]
            or "unnamed"
        )

    results_dict = {}

    def _get_result_row(results, result_name, timestep=None):
        """
        Return one result timestep as a pandas Series indexed by link ID.

        If timestep is None, the final simulation timestep is used.
        """
        result_df = results.link[result_name]

        if timestep is None:
            return result_df.iloc[-1].copy()

        if timestep in result_df.index:
            return result_df.loc[timestep].copy()

        # Use the closest available simulation timestep.
        nearest_index = min(result_df.index, key=lambda value: abs(value - timestep))
        return result_df.loc[nearest_index].copy()

    def _get_node_result_row(results, result_name, timestep=None):
        result_df = results.node[result_name]

        if timestep is None:
            return result_df.iloc[-1].copy()

        if timestep in result_df.index:
            return result_df.loc[timestep].copy()

        nearest_index = min(result_df.index, key=lambda value: abs(value - timestep))
        return result_df.loc[nearest_index].copy()


    def trace_flushing_path(
        wn,
        starting_node_name,
        base_velocity,
        flushing_velocity,
        already_flushed,
        velocity_limit_fps,
        velocity_multiplier,
        pipes_to_reflush=DEFAULT_PIPES_TO_REFLUSH,
    ):
        velocity_limit_mps = velocity_limit_fps / METERS_TO_FEET

        pipe_adjacency = {}

        for pipe_name, pipe in wn.pipes():
            start_node = pipe.start_node_name
            end_node = pipe.end_node_name

            pipe_adjacency.setdefault(start_node, []).append(
                (pipe_name, end_node)
            )
            pipe_adjacency.setdefault(end_node, []).append(
                (pipe_name, start_node)
            )

        qualifying_pipes = []
        visited_pipes = set()
        visited_nodes = set()

        # Depth-first search beginning at the specified node.
        nodes_to_visit = [starting_node_name]

        pipe_count = 0

        while nodes_to_visit:
            current_node = nodes_to_visit.pop()

            if current_node in visited_nodes:
                continue

            visited_nodes.add(current_node)

            for pipe_name, other_node_name in pipe_adjacency.get(
                current_node, []
            ):
                if pipe_name in visited_pipes:
                    continue

                visited_pipes.add(pipe_name)

                pipe_velocity = flushing_velocity.get(pipe_name)
                base_pipe_velocity = base_velocity.get(pipe_name)

                # Skip pipes without simulation velocity results.
                if pipe_velocity is None:
                    continue
                
                if base_pipe_velocity is None:
                    continue
                
                if base_pipe_velocity == 0:
                    flush_ratio = float('inf')
                else:
                    flush_ratio = pipe_velocity / base_pipe_velocity

                pipe_not_already_flushed = pipe_name not in already_flushed 
                
                if wn.get_link(pipe_name).link_type.lower() == "pipe":
                    if pipe_count >= pipes_to_reflush:
                        is_flushed = (pipe_velocity > velocity_limit_mps and flush_ratio > velocity_multiplier and pipe_not_already_flushed)
                    else:
                        is_flushed = (pipe_velocity > velocity_limit_mps and flush_ratio > velocity_multiplier)
                else:
                    is_flushed = False

                if is_flushed:
                    qualifying_pipes.append(pipe_name)
                    already_flushed.add(pipe_name)

                    if not pipe_not_already_flushed:
                        pipe_count += 1

                    # Only continue through the network when the pipe exceeds
                    # the velocity limit.
                    if other_node_name not in visited_nodes:
                        nodes_to_visit.append(other_node_name)

        return qualifying_pipes


    def get_flushing_results(
            wn,
            base_results,
            flush_results,
            sequence_name,
            operation_name,
            hydrant_node_ids,
            already_flushed=None,
            velocity_multiplier=DEFAULT_START_TO_FLUSH_VELOCITY_RATIO,
            minimum_flush_velocity_fps=DEFAULT_MIN_FLUSH_VELOCITY_FPS,
            volume_turnovers=DEFAULT_VOLUME_TURNOVERS,
            pipes_to_reflush=DEFAULT_PIPES_TO_REFLUSH,
            timestep=None):

        
        operation_results = {
            "sequence_name": sequence_name,
            "operation_name": operation_name,
            "hydrant_nodes": list(hydrant_node_ids),
            "warnings": [],

            "flushed_pipes": [],
            "flushed_pipe_velocity_fps": [],
            "pipe_velocity_fps": {},
            "base_pipe_velocity_fps": [],
            "flush_pipe_flow_gpm": [],

            "pipe_diameter_in": [],
            "pipe_length_ft": [],
            "pipe_volume_gal": [],
            "velocity_ratio": [],
            
            "total_flush_volume_gal": None,
            "total_flush_time_min": None,
            "total_flush_length_ft": None,
            "options": {},
        }
        
        if already_flushed is None:
            already_flushed = set()
        elif not isinstance(already_flushed, set):
            already_flushed = set(already_flushed)

        base_velocity_mps = _get_result_row(
            base_results,
            "velocity",
            timestep
        )

        flush_velocity_mps = _get_result_row(
            flush_results,
            "velocity",
            timestep
        )

        flush_flowrate_m3s = _get_result_row(
            flush_results,
            "flowrate",
            timestep
        )

        def velocity_to_fps(velocity_mps):
            if velocity_mps is None:
                return None
            try:
                velocity_value = float(velocity_mps)
            except (TypeError, ValueError):
                return None
            if not math.isfinite(velocity_value):
                return None
            return float(velocity_value * METERS_TO_FEET)

        operation_results["pipe_velocity_fps"] = {
            pipe_id: velocity_to_fps(flush_velocity_mps.get(pipe_id))
            for pipe_id, _ in wn.pipes()
        }
        
        flushed_pipes = []
        
        for hydrant_node_id in hydrant_node_ids:
            if hydrant_node_id not in wn.node_name_list:
                operation_results["trace_stops"].append({
                    "hydrant_node": hydrant_node_id,
                    "node": hydrant_node_id,
                    "pipe": None,
                    "reason": "Hydrant node not found in model",
                })
                continue
            
            flushed_pipes = trace_flushing_path(
                wn,
                hydrant_node_id,
                base_velocity_mps,
                flush_velocity_mps,
                already_flushed,
                minimum_flush_velocity_fps,
                velocity_multiplier,
                pipes_to_reflush,
            )
            
            if len(flushed_pipes) > 0:
                for pipe_id in flushed_pipes:
                    flush_velocity = (
                        float(flush_velocity_mps.get(pipe_id)) * METERS_TO_FEET
                    )
                    base_velocity = (
                        float(base_velocity_mps.get(pipe_id)) * METERS_TO_FEET
                    )
                    flow_gpm = float(
                        flush_flowrate_m3s.get(pipe_id)
                    ) * CUBIC_METERS_PER_SECOND_TO_GALLONS_PER_MINUTE
                    
                    pipe = wn.get_link(pipe_id)
        
                    diameter_m = float(pipe.diameter)
                    length_m = float(pipe.length)
        
                    # Internal pipe volume based on the modeled inside diameter.
                    cross_section_area_m2 = (
                        math.pi * diameter_m ** 2 / 4.0
                    )
                    pipe_volume_m3 = cross_section_area_m2 * length_m
        
                    pipe_volume_gal = (
                        pipe_volume_m3 * CUBIC_METERS_TO_GALLONS
                    )
        
                    if base_velocity > 0.0:
                        velocity_ratio = flush_velocity / base_velocity
                    elif flush_velocity > 0.0:
                        velocity_ratio = float("inf")
                    else:
                        velocity_ratio = None
        
                    operation_results["flushed_pipes"].append(pipe_id)
                    operation_results["flushed_pipe_velocity_fps"].append(
                        float(flush_velocity)
                    )
                    operation_results["base_pipe_velocity_fps"].append(
                        float(base_velocity)
                    )
                    operation_results["flush_pipe_flow_gpm"].append(
                        float(abs(flow_gpm))
                    )
        
                    operation_results["pipe_diameter_in"].append(
                        round(diameter_m * METERS_TO_INCHES, 1)
                    )
                    operation_results["pipe_length_ft"].append(
                        round(length_m * METERS_TO_FEET, 1)
                    )
                    operation_results["pipe_volume_gal"].append(
                        round(pipe_volume_gal, 1)
                    )
                    operation_results["velocity_ratio"].append(
                        str(velocity_ratio)
                    )
                
                
                pipe_volumes = sum(operation_results['pipe_volume_gal'])
        
                flush_flowrate = sum(operation_results["flush_pipe_flow_gpm"]) / len(operation_results["flush_pipe_flow_gpm"])
                
                flush_volume = pipe_volumes * volume_turnovers
                
                flush_time = flush_volume / flush_flowrate

                flush_length = sum(operation_results["pipe_length_ft"])
                
                operation_results['total_flush_time_min'] = float(
                    round(flush_time, 2)
                )
                operation_results['total_flush_volume_gal'] = float(
                    round(flush_volume, 1)
                )
                operation_results['total_flush_length_ft'] = float(
                    round(flush_length, 1)
                )

        return operation_results, already_flushed


    results_dict = {}
    already_flushed = set()

    base_wn = wntr.network.WaterNetworkModel(inp_file)

    sim = wntr.sim.EpanetSimulator(base_wn)
    if progress_callback:
        progress_callback(5, "Running the baseline network simulation...")
    base_results = sim.run_sim()
    if progress_callback:
        progress_callback(15, "Baseline simulation complete. Preparing operations...")

    base_velocity = (
        base_results.link["velocity"].transpose() * METERS_TO_FEET
    )
    base_velocity.columns = ['velocity']

    total_operations = sum(
        len(sequence.get("operations", [])) for sequence in sequences
    )
    completed_operations = 0

    for sequence in sequences:
        for seq_name in model_store['results_dict']:
            if seq_name == sequence['name']:
                break
            for op_name in model_store['results_dict'][seq_name]:
                previously_flushed_pipes = model_store['results_dict'][seq_name][op_name].get(
                    "flushed_pipes", []
                )
                if isinstance(previously_flushed_pipes, (list, tuple, set)):
                    already_flushed.update(previously_flushed_pipes)

        seq_wn = wntr.network.WaterNetworkModel(inp_file)

        results_dict[sequence["name"]] = {}
        for operation in sequence["operations"]:
            operation_progress = 15 + int(
                80 * completed_operations / max(1, total_operations)
            )
            if progress_callback:
                progress_callback(
                    operation_progress,
                    f"Running {sequence['name']} - {operation.get('name', 'operation')}...",
                )
            inp_filename = (
                f"{_filename_part(sequence['name'])}_"
                f"{_filename_part(operation['name'])}.inp"
            )
            updated_inp = os.path.join(model_dir, inp_filename)

            valves_to_close = operation.get("close_valves", []) or []
            valves_to_open = operation.get("open_valves", []) or []
            hydrants_to_open = operation.get("open_hydrants", []) or []

            operation_options = operation.get("options")
            if operation_options is None:
                operation_options = {}
            if not isinstance(operation_options, dict):
                raise ValueError(
                    f"Options for operation '{operation.get('name', '')}' must be an object."
                )

            def operation_numeric_option(name, fallback, legacy_value=None):
                value = operation_options.get(name)
                if value is None or value == "":
                    value = legacy_value
                if value is None or value == "":
                    return fallback
                try:
                    numeric_value = float(value)
                except (TypeError, ValueError) as exc:
                    raise ValueError(
                        f"Operation option '{name}' for "
                        f"'{operation.get('name', '')}' must be numeric."
                    ) from exc
                if not math.isfinite(numeric_value) or numeric_value <= 0:
                    raise ValueError(
                        f"Operation option '{name}' for "
                        f"'{operation.get('name', '')}' must be a finite number greater than zero."
                    )
                return numeric_value

            operation_orifice_diam = operation_numeric_option(
                "default_orifice_diam",
                default_orifice_diam,
                operation.get("orifice_size"),
            )
            operation_velocity_multiplier = operation_numeric_option(
                "start_vel_to_flushing_vel_ratio", velocity_multiplier
            )
            operation_min_flush_velocity_fps = operation_numeric_option(
                "min_flush_vel", minimum_flush_velocity_fps
            )
            operation_volume_turnovers = operation_numeric_option(
                "volume_turnovers", volume_turnovers
            )
            raw_pipes_to_reflush = operation_options.get("pipes_to_reflush")
            if raw_pipes_to_reflush is None or raw_pipes_to_reflush == "":
                raw_pipes_to_reflush = pipes_to_reflush
            try:
                operation_pipes_to_reflush_value = float(raw_pipes_to_reflush)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"Operation option 'pipes_to_reflush' for "
                    f"'{operation.get('name', '')}' must be an integer."
                ) from exc
            if (
                not math.isfinite(operation_pipes_to_reflush_value)
                or operation_pipes_to_reflush_value < 0
                or not operation_pipes_to_reflush_value.is_integer()
            ):
                raise ValueError(
                    f"Operation option 'pipes_to_reflush' for "
                    f"'{operation.get('name', '')}' must be a non-negative integer."
                )
            operation_pipes_to_reflush = int(operation_pipes_to_reflush_value)
            effective_operation_options = {
                "default_orifice_diam": operation_orifice_diam,
                "start_vel_to_flushing_vel_ratio": operation_velocity_multiplier,
                "min_flush_vel": operation_min_flush_velocity_fps,
                "volume_turnovers": operation_volume_turnovers,
                "pipes_to_reflush": operation_pipes_to_reflush,
            }

            emitter_coefficient = (
                ORIFICE_EMITTER_COEFFICIENT_NUMERATOR
                * (operation_orifice_diam ** 2)
                / ORIFICE_EMITTER_COEFFICIENT_DENOMINATOR
            )

            for valve in valves_to_close:
                if valve in mapping['valves']:
                    pipe_id = mapping['valves'][valve]
                    pipe = seq_wn.get_link(pipe_id)
                    pipe.initial_status = 'Closed'
            for valve in valves_to_open:
                if valve in mapping['valves']:
                    pipe_id = mapping['valves'][valve]
                    pipe = seq_wn.get_link(pipe_id)
                    pipe.initial_status = 'Open'
            for hydrant in hydrants_to_open:
                if hydrant in mapping['hydrants']:
                    junct_id = mapping['hydrants'][hydrant]
                    junct = seq_wn.get_node(junct_id)
                    junct.emitter_coefficient = emitter_coefficient
                    
            if hydrants_to_open:
                wntr.network.write_inpfile(seq_wn, updated_inp)
                if updated_inp not in generated_inp_files:
                    generated_inp_files.append(updated_inp)
            
                sim = wntr.sim.EpanetSimulator(seq_wn)
                seq_results = sim.run_sim()
            
                hydrant_node_ids = []
            
                for hydrant_id in hydrants_to_open:
                    if hydrant_id not in mapping["hydrants"]:
                        print(
                            f"[WARNING] Hydrant {hydrant_id} was not found "
                            f"in mapping['hydrants']."
                        )
                        continue
            
                    hydrant_node_ids.append(
                        mapping["hydrants"][hydrant_id]
                    )
            
                operation_results, already_flushed = get_flushing_results(
                    wn=seq_wn,
                    base_results=base_results,
                    flush_results=seq_results,
                    sequence_name=sequence["name"],
                    operation_name=operation["name"],
                    hydrant_node_ids=hydrant_node_ids,
                    already_flushed=already_flushed,
                    velocity_multiplier=operation_velocity_multiplier,
                    minimum_flush_velocity_fps=operation_min_flush_velocity_fps,
                    volume_turnovers=operation_volume_turnovers,
                    pipes_to_reflush=operation_pipes_to_reflush,
                    timestep=None,  # Uses final simulation timestep
                )
                operation_results["options"] = effective_operation_options

                warnings = []
                total_flush_length_ft = operation_results.get(
                    "total_flush_length_ft"
                )
                if (
                    total_flush_length_ft is not None
                    and total_flush_length_ft > max_flush_length
                ):
                    warnings.append({
                        "check": "Maximum flush length",
                        "summary": (
                            f"Total flush length is {total_flush_length_ft:.1f} ft, "
                            f"above the {max_flush_length:.1f} ft maximum."
                        ),
                    })

                for pipe_id in operation_results["flushed_pipes"]:
                    pipe_diameter_in = float(
                        seq_wn.get_link(pipe_id).diameter
                    ) * METERS_TO_INCHES
                    if pipe_diameter_in > max_flush_diam:
                        warnings.append({
                            "check": "Maximum flush diameter",
                            "summary": (
                                f"Pipe {pipe_id} is {pipe_diameter_in:.1f} in "
                                f"in diameter, above the {max_flush_diam:.1f} in maximum."
                            ),
                        })

                hydrant_lateral_pipes = set()
                hydrant_connection_nodes = set()
                for hydrant_node_id in hydrant_node_ids:
                    for link_name, link in seq_wn.pipes():
                        if link.start_node_name == hydrant_node_id:
                            hydrant_lateral_pipes.add(link_name)
                            hydrant_connection_nodes.add(link.end_node_name)
                        elif link.end_node_name == hydrant_node_id:
                            hydrant_lateral_pipes.add(link_name)
                            hydrant_connection_nodes.add(link.start_node_name)

                flush_velocities = operation_results.get(
                    "flushed_pipe_velocity_fps", []
                )
                for pipe_id, velocity_fps in zip(
                    operation_results["flushed_pipes"], flush_velocities
                ):
                    if (
                        pipe_id not in hydrant_lateral_pipes
                        and abs(float(velocity_fps)) > max_flush_vel
                    ):
                        warnings.append({
                            "check": "Maximum flush velocity",
                            "summary": (
                                f"Pipe {pipe_id} has a flush velocity of "
                                f"{abs(float(velocity_fps)):.2f} ft/s, above the "
                                f"{max_flush_vel:.2f} ft/s maximum."
                            ),
                        })

                psi_per_meter = PSI_PER_FOOT_OF_WATER * METERS_TO_FEET
                flush_node_pressure = _get_node_result_row(
                    seq_results, "pressure"
                )
                for connection_node in sorted(hydrant_connection_nodes):
                    if connection_node not in flush_node_pressure.index:
                        raise RuntimeError(
                            f"Pressure results are missing hydrant connection node "
                            f"'{connection_node}'."
                        )
                    residual_pressure_psi = (
                        float(flush_node_pressure[connection_node])
                        * psi_per_meter
                    )
                    if residual_pressure_psi <= min_res_pres:
                        warnings.append({
                            "check": "Minimum residual pressure",
                            "summary": (
                                f"Node {connection_node} has residual pressure of "
                                f"{residual_pressure_psi:.2f} psi, at or below the "
                                f"{min_res_pres:.2f} psi minimum."
                            ),
                        })

                #base_node_pressure = _get_node_result_row(
                #    base_results, "pressure"
                #)
                #pressure_drop_limit_m = pres_drop_warning_limit / psi_per_meter
                #shared_nodes = (
                #    base_node_pressure.index.intersection(
                #        flush_node_pressure.index
                #    )
                #)
                #for node_name in shared_nodes:
                    #pressure_drop_m = (
                    #    float(base_node_pressure[node_name])
                    #    - float(flush_node_pressure[node_name])
                    #)
                    #if pressure_drop_m > pressure_drop_limit_m:
                    #    pressure_drop_psi = (
                    #        pressure_drop_m * psi_per_meter
                    #    )
                    #    warnings.append({
                    #        "check": "Pressure drop",
                    #        "summary": (
                    #            f"Node {node_name} pressure dropped "
                    #            f"{pressure_drop_psi:.2f} psi from the base model, "
                    #            f"above the {pres_drop_warning_limit:.2f} psi limit."
                    #        ),
                    #    })

                operation_results["warnings"] = warnings

                results_dict[sequence["name"]][operation["name"]] = (
                    operation_results
                )
            
                for hydrant in hydrants_to_open:
                    if hydrant in mapping["hydrants"]:
                        junct_id = mapping['hydrants'][hydrant]
                        junct = seq_wn.get_node(junct_id)
                        junct.emitter_coefficient = 0

            completed_operations += 1
            if progress_callback:
                operation_progress = 15 + int(
                    80 * completed_operations / max(1, total_operations)
                )
                progress_callback(
                    operation_progress,
                    f"Completed {sequence['name']} - {operation.get('name', 'operation')}.",
                )

    if total_operations == 0 and progress_callback:
        progress_callback(95, "No operations to simulate.")

    return results_dict

        
