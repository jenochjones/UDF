#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Oct 11 08:51:27 2026

@author: jonjones
"""
import wntr



"""
Run the water network model using the provided model store.

Args:
    model_store (dict): A dictionary containing the water network model and other relevant data.
    sequences (list): A list of sequences to be processed.

Returns:
    dict: The updated model store after running the model.
"""

sequences = [{
    "name": "Z1-33",
    "operations": [
        {
            "name": "01",
            "close_valves": ["V522", "V523", "V521", "V517"],
            "open_valves": [],
            "open_hydrants": [],
            "orifice_size": "",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "Close Valves",
        },
        {
            "name": "02",
            "close_valves": ["V1783", "V1784", "V387", "V401", "V403"],
            "open_valves": [],
            "open_hydrants": [],
            "orifice_size": "",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "Close Valves",
        },
        {
            "name": "03",
            "close_valves": ["V1408", "V2284", "V2449"],
            "open_valves": [],
            "open_hydrants": [],
            "orifice_size": "",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "Close Valves",
        },
        {
            "name": "04",
            "close_valves": [],
            "open_valves": [],
            "open_hydrants": ["H636"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "05",
            "close_valves": ["V2285", "V2287"],
            "open_valves": ["V403", "V2284"],
            "open_hydrants": ["H121"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "06",
            "close_valves": [],
            "open_valves": ["V1408", "V2285", "V2287"],
            "open_hydrants": ["H125"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "07",
            "close_valves": ["V2132"],
            "open_valves": [],
            "open_hydrants": ["H899"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "08",
            "close_valves": ["V2131"],
            "open_valves": ["V2132"],
            "open_hydrants": ["H899"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "09",
            "close_valves": [],
            "open_valves": ["V2131"],
            "open_hydrants": ["H1027"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "10",
            "close_valves": ["V2326"],
            "open_valves": ["V2449"],
            "open_hydrants": ["H13"],
            "orifice_size": "3.0",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "11",
            "close_valves": [],
            "open_valves": [],
            "open_hydrants": ["H12"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "12",
            "close_valves": [],
            "open_valves": ["V517", "V521", "V522", "V523"],
            "open_hydrants": ["H512"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "13",
            "close_valves": [],
            "open_valves": [],
            "open_hydrants": ["H919"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "14",
            "close_valves": [],
            "open_valves": [],
            "open_hydrants": ["H765"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "15",
            "close_valves": [],
            "open_valves": [],
            "open_hydrants": ["H413"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "16",
            "close_valves": [],
            "open_valves": [],
            "open_hydrants": ["H1016"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "17",
            "close_valves": ["V2430"],
            "open_valves": ["V1784"],
            "open_hydrants": ["H744"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "18",
            "close_valves": ["V2330", "V2334", "V2349", "V2342", "V1784"],
            "open_valves": ["V2326", "V2430"],
            "open_hydrants": [],
            "orifice_size": "",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "19",
            "close_valves": [],
            "open_valves": [],
            "open_hydrants": ["H971"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "20",
            "close_valves": ["V2341"],
            "open_valves": ["V2334"],
            "open_hydrants": ["H971"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "21",
            "close_valves": [],
            "open_valves": [],
            "open_hydrants": ["H970"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "22",
            "close_valves": ["V2340"],
            "open_valves": ["V2349"],
            "open_hydrants": ["H970"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "23",
            "close_valves": ["V2353"],
            "open_valves": ["V2340", "V2342"],
            "open_hydrants": ["H971"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "24",
            "close_valves": ["V2329", "V2349"],
            "open_valves": ["V2341", "V2353", "V2330"],
            "open_hydrants": ["H977"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "25",
            "close_valves": [],
            "open_valves": ["V2329", "V2349"],
            "open_hydrants": [],
            "orifice_size": "",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "26",
            "close_valves": [],
            "open_valves": [],
            "open_hydrants": ["H744"],
            "orifice_size": "3.0",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "Flush at 2,000 gpm",
        },
        {
            "name": "27",
            "close_valves": [],
            "open_valves": ["V1784"],
            "open_hydrants": ["H360"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "28",
            "close_valves": ["V1500"],
            "open_valves": [],
            "open_hydrants": ["H631"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "29",
            "close_valves": ["V1499"],
            "open_valves": ["V1500"],
            "open_hydrants": ["H631"],
            "orifice_size": "2.5",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "",
        },
        {
            "name": "30",
            "close_valves": [],
            "open_valves": ["V387", "V401", "V1783", "V1499"],
            "open_hydrants": [],
            "orifice_size": "",
            "target_velocity": "",
            "toggle_mode": "Orifice Size",
            "map_message": "All valves back to normal",
        },
    ],
}]




#inp_file = r'C:\WebApps\UDF\flushing_journal_app\temp\updated.inp'
#rpt_file = r'C:\WebApps\UDF\flushing_journal_app\temp\updated.rpt'
#bin_file = r'C:\WebApps\UDF\flushing_journal_app\temp\updated.bin'

inp_file = './updatedSS.inp'
rpt_file = './updated.rpt'
bin_file = './updated.bin'

results_dict = {}

namespace = {}; exec(open('./my_dict.txt').read(), namespace); mapping = namespace['mapping']

#wn = wntr.network.io.read_inpfile(inp_file)


import math
from collections import deque

import wntr


# WNTR stores model geometry in SI units.
M_TO_FT = 3.280839895
M_TO_IN = 39.37007874
M3S_TO_GPM = 15850.323141489
M3_TO_GAL = 264.172052358


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


def _get_upstream_pipe_candidates(wn, current_node_id, flowrate_m3s):
    """
    Find pipes that hydraulically deliver flow into current_node_id.

    WNTR/EPANET flow sign convention:
        Positive flow: start_node -> end_node
        Negative flow: end_node -> start_node

    Returns:
        list of tuples:
            (pipe_id, upstream_node_id, absolute_flow_m3s)
    """
    candidates = []

    for link_id in wn.get_links_for_node(current_node_id):
        link = wn.get_link(link_id)

        # The flushing calculations requested here are pipe-specific.
        if not isinstance(link, wntr.network.elements.Pipe):
            continue

        if link_id not in flowrate_m3s.index:
            continue

        flow = float(flowrate_m3s.loc[link_id])

        # Positive flow enters the current node when current node is the
        # pipe's end node.
        if flow > 0.0 and link.end_node_name == current_node_id:
            candidates.append(
                (link_id, link.start_node_name, abs(flow))
            )

        # Negative flow enters the current node when current node is the
        # pipe's start node.
        elif flow < 0.0 and link.start_node_name == current_node_id:
            candidates.append(
                (link_id, link.end_node_name, abs(flow))
            )

    # Follow the highest-flow branch first. This also makes output ordering
    # repeatable when more than one pipe supplies a junction.
    candidates.sort(key=lambda item: item[2], reverse=True)

    return candidates


def trace_flushed_pipes(
        wn,
        base_results,
        flush_results,
        sequence_name,
        operation_name,
        hydrant_node_ids,
        already_flushed=None,
        velocity_multiplier=3.0,
        minimum_flush_velocity_fps=5.0,
        timestep=None):
    """
    Trace flow upstream from one or more hydrant nodes.

    A pipe is recorded when:

        absolute flush velocity >= velocity_multiplier
                                   * absolute base velocity

    Tracing along a branch stops when:
        1. The pipe fails the velocity criterion.
        2. The pipe is already in already_flushed.
        3. The pipe has already been encountered during this operation.
        4. No pipe hydraulically delivers flow to the current node.

    Parameters
    ----------
    wn : wntr.network.WaterNetworkModel
        Network used for the flush simulation.

    base_results : wntr.sim.results.SimulationResults
        Results from the unmodified/base model.

    flush_results : wntr.sim.results.SimulationResults
        Results from the flushing operation.

    sequence_name : str
        Flushing sequence name.

    operation_name : str
        Flushing operation name.

    hydrant_node_ids : list[str]
        Model junction IDs associated with the open hydrants.

    already_flushed : set[str] or list[str], optional
        Pipes flushed by previous operations. The supplied set is updated
        in place. If a list is supplied, a new set is created.

    velocity_multiplier : float, optional
        Required ratio between flush and base velocity. Default is 3.0.

    timestep : int or float, optional
        Simulation time in seconds. If omitted, final results are used.

    Returns
    -------
    tuple
        operation_results, already_flushed

        operation_results is a dictionary containing lists of pipe IDs,
        velocities, flows, dimensions, volumes, and flushing times.
    """
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

    operation_results = {
        "sequence_name": sequence_name,
        "operation_name": operation_name,
        "hydrant_nodes": list(hydrant_node_ids),

        "flushed_pipes": [],
        "flushed_pipe_velocity_fps": [],
        "base_pipe_velocity_fps": [],
        "flush_pipe_flow_gpm": [],

        "pipe_diameter_in": [],
        "pipe_length_ft": [],
        "pipe_volume_gal": [],
        "three_pipe_volumes_gal": [],
        "flush_time_min": [],

        # Helpful fields for reviewing branches and stopping conditions.
        "source_hydrant_node": [],
        "upstream_node": [],
        "velocity_ratio": [],
        "trace_stops": [],
    }

    # One queue item represents one active upstream branch.
    trace_queue = deque()

    for hydrant_node_id in hydrant_node_ids:
        if hydrant_node_id not in wn.node_name_list:
            operation_results["trace_stops"].append({
                "hydrant_node": hydrant_node_id,
                "node": hydrant_node_id,
                "pipe": None,
                "reason": "Hydrant node not found in model",
            })
            continue

        trace_queue.append((hydrant_node_id, hydrant_node_id))

    # Prevent loops and duplicate records within this operation.
    visited_pipes = set()

    while trace_queue:
        current_node_id, source_hydrant_id = trace_queue.popleft()

        upstream_candidates = _get_upstream_pipe_candidates(
            wn=wn,
            current_node_id=current_node_id,
            flowrate_m3s=flush_flowrate_m3s
        )

        if not upstream_candidates:
            operation_results["trace_stops"].append({
                "hydrant_node": source_hydrant_id,
                "node": current_node_id,
                "pipe": None,
                "reason": "No upstream pipe with flow entering node",
            })
            continue

        for pipe_id, upstream_node_id, absolute_flow_m3s in upstream_candidates:

            if pipe_id in already_flushed:
                operation_results["trace_stops"].append({
                    "hydrant_node": source_hydrant_id,
                    "node": current_node_id,
                    "pipe": pipe_id,
                    "reason": "Pipe is in already_flushed",
                })
                continue

            if pipe_id in visited_pipes:
                operation_results["trace_stops"].append({
                    "hydrant_node": source_hydrant_id,
                    "node": current_node_id,
                    "pipe": pipe_id,
                    "reason": "Pipe already visited in this operation",
                })
                continue

            visited_pipes.add(pipe_id)

            if pipe_id not in flush_velocity_mps.index:
                operation_results["trace_stops"].append({
                    "hydrant_node": source_hydrant_id,
                    "node": current_node_id,
                    "pipe": pipe_id,
                    "reason": "Flush velocity result is unavailable",
                })
                continue

            if pipe_id not in base_velocity_mps.index:
                operation_results["trace_stops"].append({
                    "hydrant_node": source_hydrant_id,
                    "node": current_node_id,
                    "pipe": pipe_id,
                    "reason": "Base velocity result is unavailable",
                })
                continue

            flush_velocity = abs(float(flush_velocity_mps.loc[pipe_id]))
            base_velocity = abs(float(base_velocity_mps.loc[pipe_id]))
            
            required_velocity = velocity_multiplier * base_velocity

            meets_criterion = (
                flush_velocity * M_TO_FT >= minimum_flush_velocity_fps
                and flush_velocity >= required_velocity
            )

            if meets_criterion:
                operation_results["trace_stops"].append({
                    "hydrant_node": source_hydrant_id,
                    "node": current_node_id,
                    "pipe": pipe_id,
                    "reason": "Flush velocity is below required multiple",
                    "flush_velocity_fps":
                        flush_velocity * M_TO_FT,
                    "base_velocity_fps":
                        base_velocity * M_TO_FT,
                    "required_velocity_fps":
                        required_velocity * M_TO_FT,
                })
                continue

            pipe = wn.get_link(pipe_id)

            diameter_m = float(pipe.diameter)
            length_m = float(pipe.length)

            # Internal pipe volume based on the modeled inside diameter.
            cross_section_area_m2 = (
                math.pi * diameter_m ** 2 / 4.0
            )
            pipe_volume_m3 = cross_section_area_m2 * length_m

            pipe_volume_gal = pipe_volume_m3 * M3_TO_GAL
            three_pipe_volumes_gal = 3.0 * pipe_volume_gal
            flow_gpm = absolute_flow_m3s * M3S_TO_GPM

            if flow_gpm > 0.0:
                flush_time_min = three_pipe_volumes_gal / flow_gpm
            else:
                flush_time_min = None

            if base_velocity > 0.0:
                velocity_ratio = flush_velocity / base_velocity
            elif flush_velocity > 0.0:
                velocity_ratio = float("inf")
            else:
                velocity_ratio = None

            operation_results["flushed_pipes"].append(pipe_id)
            operation_results["flushed_pipe_velocity_fps"].append(
                flush_velocity * M_TO_FT
            )
            operation_results["base_pipe_velocity_fps"].append(
                base_velocity * M_TO_FT
            )
            operation_results["flush_pipe_flow_gpm"].append(flow_gpm)

            operation_results["pipe_diameter_in"].append(
                diameter_m * M_TO_IN
            )
            operation_results["pipe_length_ft"].append(
                length_m * M_TO_FT
            )
            operation_results["pipe_volume_gal"].append(
                pipe_volume_gal
            )
            operation_results["three_pipe_volumes_gal"].append(
                three_pipe_volumes_gal
            )
            operation_results["flush_time_min"].append(
                flush_time_min
            )

            operation_results["source_hydrant_node"].append(
                source_hydrant_id
            )
            operation_results["upstream_node"].append(
                upstream_node_id
            )
            operation_results["velocity_ratio"].append(
                velocity_ratio
            )

            already_flushed.add(pipe_id)

            # Continue tracing from the upstream end of this pipe.
            trace_queue.append(
                (upstream_node_id, source_hydrant_id)
            )

    return operation_results, already_flushed



results_dict = {}
already_flushed = set()

base_wn = wntr.network.WaterNetworkModel(inp_file)

sim = wntr.sim.EpanetSimulator(base_wn)
base_results = sim.run_sim()

base_velocity = base_results.link['velocity'].transpose() * 3.28084
base_velocity.columns = ['velocity']

for sequence in sequences:
    seq_wn = wntr.network.WaterNetworkModel(inp_file)

    print(f"[DEBUG] Processing sequence: {sequence['name']}")
    results_dict[sequence["name"]] = {}
    for operation in sequence["operations"]:

        #updated_inp = r'C:\WebApps\UDF\flushing_journal_app\temp\\' + f"{sequence['name']}_{operation['name']}.inp"
        
        updated_inp = './inpFiles/' + f"{sequence['name']}_{operation['name']}.inp"

        valves_to_close = operation.get("close_valves", []) or []
        valves_to_open = operation.get("open_valves", []) or []
        hydrants_to_open = operation.get("open_hydrants", []) or []
        
        print(f'Opening: {valves_to_open}')
        print(f'Closing: {valves_to_close}')
        print(f'Flushing: {hydrants_to_open}')

        orifice_size = orifice_size = float(operation.get("orifice_size") or 2.5)

        emitter_coefficient = 28.35 * (orifice_size ** 2) / 13293.8648 if orifice_size is not None else None

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
        
            operation_results, already_flushed = trace_flushed_pipes(
                wn=seq_wn,
                base_results=base_results,
                flush_results=seq_results,
                sequence_name=sequence["name"],
                operation_name=operation["name"],
                hydrant_node_ids=hydrant_node_ids,
                already_flushed=already_flushed,
                velocity_multiplier=3.0,
                timestep=None,  # Uses final simulation timestep
            )
        
            results_dict[sequence["name"]][operation["name"]] = (
                operation_results
            )
        
            print(
                "[DEBUG] Flushed pipes:",
                operation_results["flushed_pipes"]
            )
            
            
            
            for hydrant in hydrants_to_open:
                if hydrant in mapping["hydrants"]:
                    junct_id = mapping['hydrants'][hydrant]
                    junct = seq_wn.get_node(junct_id)
                    junct.emitter_coefficient = emitter_coefficient
    