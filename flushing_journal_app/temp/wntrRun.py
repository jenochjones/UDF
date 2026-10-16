#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Oct 11 08:51:27 2026

@author: jonjones
"""

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


def trace_flushing_path(wn, starting_node_name, base_velocity, flushing_velocity, already_flushed, velocity_limit_fps, velocity_multiplier):
    velocity_limit_mps = velocity_limit_fps / M_TO_FT

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
            
            is_flushed = (pipe_velocity > velocity_limit_mps and flush_ratio > velocity_multiplier and pipe_name not in already_flushed)

            if is_flushed:
                qualifying_pipes.append(pipe_name)
                already_flushed.add(pipe_name)

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
        velocity_multiplier=3.0,
        minimum_flush_velocity_fps=5.0,
        timestep=None):

    
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
        "velocity_ratio": [],
        
        "total_flush_volume_gal": None,
        "total_flush_time_min": None,
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
    
    flushed_pipes = []
    
    for hydrant_node_id in hydrant_node_ids:
        print(f'Sequence: {sequence_name}')
        print(f'Operation: {operation_name}')
        print(f'Hydrant: {hydrant_node_id}')
        if hydrant_node_id not in wn.node_name_list:
            operation_results["trace_stops"].append({
                "hydrant_node": hydrant_node_id,
                "node": hydrant_node_id,
                "pipe": None,
                "reason": "Hydrant node not found in model",
            })
            continue
        
        flushed_pipes = trace_flushing_path(wn, hydrant_node_id, base_velocity_mps, flush_velocity_mps, already_flushed, minimum_flush_velocity_fps, velocity_multiplier)
        
        if len(flushed_pipes) > 0:
            for pipe_id in flushed_pipes:
                flush_velocity = flush_velocity_mps.get(pipe_id) * M_TO_FT
                base_velocity = base_velocity_mps.get(pipe_id) * M_TO_FT
                flow_gpm = flush_flowrate_m3s.get(pipe_id) * M3S_TO_GPM
                
                pipe = wn.get_link(pipe_id)
    
                diameter_m = float(pipe.diameter)
                length_m = float(pipe.length)
    
                # Internal pipe volume based on the modeled inside diameter.
                cross_section_area_m2 = (
                    math.pi * diameter_m ** 2 / 4.0
                )
                pipe_volume_m3 = cross_section_area_m2 * length_m
    
                pipe_volume_gal = pipe_volume_m3 * M3_TO_GAL
    
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
                operation_results["flush_pipe_flow_gpm"].append(abs(flow_gpm))
    
                operation_results["pipe_diameter_in"].append(
                    round(diameter_m * M_TO_IN, 1)
                )
                operation_results["pipe_length_ft"].append(
                    round(length_m * M_TO_FT, 1)
                )
                operation_results["pipe_volume_gal"].append(
                    round(pipe_volume_gal, 1)
                )
                operation_results["velocity_ratio"].append(
                    str(velocity_ratio)
                )
            
            
            pipe_volumes = sum(operation_results['pipe_volume_gal'])
    
            flush_flowrate = sum(operation_results["flush_pipe_flow_gpm"]) / len(operation_results["flush_pipe_flow_gpm"])
            
            flush_volume = pipe_volumes * 3
            
            flush_time = flush_volume / flush_flowrate
            
            operation_results['total_flush_time_min'] = round(flush_time, 2)
            operation_results['total_flush_volume_gal'] = round(flush_volume, 1)

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

    results_dict[sequence["name"]] = {}
    for operation in sequence["operations"]:

        #updated_inp = r'C:\WebApps\UDF\flushing_journal_app\temp\\' + f"{sequence['name']}_{operation['name']}.inp"
        
        updated_inp = './inpFiles/' + f"{sequence['name']}_{operation['name']}.inp"

        valves_to_close = operation.get("close_valves", []) or []
        valves_to_open = operation.get("open_valves", []) or []
        hydrants_to_open = operation.get("open_hydrants", []) or []

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
        
            operation_results, already_flushed = get_flushing_results(
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
        
            for hydrant in hydrants_to_open:
                if hydrant in mapping["hydrants"]:
                    junct_id = mapping['hydrants'][hydrant]
                    junct = seq_wn.get_node(junct_id)
                    junct.emitter_coefficient = 0
    