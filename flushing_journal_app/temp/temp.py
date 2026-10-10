#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Oct  4 20:12:01 2026

@author: jonjones
"""
import ctypes
from ctypes import byref
from wntr.epanet.util import SizeLimits
from wntr.epanet import toolkit as en

import pandas as pd


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



def get_link_id(en, link_index):
    """
    Get the EPANET link ID from a link index.

    Parameters
    ----------
    en : wntr.epanet.toolkit.ENepanet
        Open EPANET toolkit object.
    link_index : int
        1-based EPANET link index.

    Returns
    -------
    str
        Link ID/name.
    """
    buffer = ctypes.create_string_buffer(SizeLimits.EN_MAX_ID.value)

    if en._project is not None:
        en.errcode = en.ENlib.EN_getlinkid(
            en._project,
            link_index,
            byref(buffer)
        )
    else:
        en.errcode = en.ENlib.ENgetlinkid(
            link_index,
            byref(buffer)
        )

    en._error()

    return buffer.value.decode("utf-8")


def close_epanet_model(en_model):
    """
    Safely close an EPANET hydraulic analysis and project.
    """
    if en_model is None:
        return

    try:
        en_model.ENcloseH()
    except Exception:
        pass

    try:
        en_model.ENclose()
    except Exception:
        pass


def reset_epanet_model(inp_file, rpt_file, bin_file, model_time_hours):
    """
    Create a fresh EPANET model from the original INP file.

    Each call returns a new ENepanet instance, so all valve statuses,
    emitter coefficients, hydraulic results, and simulation time are
    reset to the values in the original INP file.
    """
    en_model = en.ENepanet()
    en_model.ENopen(inp_file, rpt_file, bin_file)

    en_model.ENopenH()
    en_model.ENinitH(0)

    # Advance the fresh model to the requested model time.
    target_time = model_time_hours * 3600
    hydraulic_time = 0

    while hydraulic_time < target_time:
        hydraulic_time = en_model.ENrunH()

        if hydraulic_time >= target_time:
            break

        hydraulic_step = en_model.ENnextH()

        if hydraulic_step <= 0:
            break

    return en_model




model_time = 9 # Default to 24 hours if not specified

inp_file = r'C:\WebApps\UDF\flushing_journal_app\temp\updated.inp'
rpt_file = r'C:\WebApps\UDF\flushing_journal_app\temp\updated.rpt'
bin_file = r'C:\WebApps\UDF\flushing_journal_app\temp\updated.bin'

results_dict = {}

namespace = {}; exec(open(r'C:\WebApps\UDF\flushing_journal_app\temp\my_dict.txt').read(), namespace); mapping = namespace['mapping']

enData = reset_epanet_model(inp_file, rpt_file, bin_file, model_time)

base_n_links = enData.ENgetcount(2)

base_results = []

base_n_links = enData.ENgetcount(2)

for i in range(1, base_n_links + 1):
    
    link_id = get_link_id(enData, i)
    velocity = enData.ENgetlinkvalue(i, 9)
    flow = enData.ENgetlinkvalue(i, 8)

    base_results.append({
        "Velocity": velocity,
        "Flow": flow
    })

base_results_df = pd.DataFrame(base_results)

close_epanet_model(enData)


for sequence in sequences:
    operation_model = reset_epanet_model(inp_file, rpt_file, bin_file, model_time)
    print(f"[DEBUG] Processing sequence: {sequence['name']}")
    results_dict[sequence["name"]] = {}
    for operation in sequence["operations"]:

        updated_inp = r'C:\WebApps\UDF\flushing_journal_app\temp\\' + f"{sequence['name']}_{operation['name']}.inp"

        valves_to_close = operation.get("close_valves", []) or []
        valves_to_open = operation.get("open_valves", []) or []
        hydrants_to_open = operation.get("open_hydrants", []) or []

        orifice_size = orifice_size = float(operation.get("orifice_size") or 2.5)

        emitter_coefficient = 28.35 * (orifice_size ** 2) if orifice_size is not None else None

        for valve in valves_to_close:
            if valve in mapping:
                enData.ENsetlinkvalue(mapping[valve], 4, 0)  # Close valve

        for valve in valves_to_open:
            if valve in mapping:
                enData.ENsetlinkvalue(mapping[valve], 4, 1)  # Open valve

        for hydrant in hydrants_to_open:
            if hydrant in mapping:
                enData.ENsetnodevalue(mapping[hydrant], 3, emitter_coefficient)  # Open hydrant

        if hydrants_to_open is not []:
            operation_model.ENrunH()
            operation_model.ENsaveinpfile(updated_inp)

            n_links = operation_model.ENgetcount(2)

            results = []


            for i in range(1, n_links + 1):
                
                link_id = get_link_id(operation_model, i)
                velocity = operation_model.ENgetlinkvalue(i, 9)
                flow = operation_model.ENgetlinkvalue(i, 8)

                results.append({
                    "Velocity": velocity,
                    "Flow": flow
                })

            results_df = pd.DataFrame(results)
            
            results_dict[sequence['name']][operation['name']] = results_df

            print(results_df.head())
            
            for hydrant in hydrants_to_open:
                if hydrant in mapping:
                    enData.ENsetnodevalue(mapping[hydrant], 3, 0)  # Close hydrants

    close_epanet_model(operation_model)

    
    
    