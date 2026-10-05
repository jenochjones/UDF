#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Oct  4 20:12:01 2026

@author: jonjones
"""

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

sequences = {
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
}



import ctypes
from ctypes import byref
from wntr.epanet.util import SizeLimits

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







model_time = 9 # Default to 24 hours if not specified

inp_file = '/Users/jonjones/temp/updated.inp'
rpt_file = '/Users/jonjones/temp/updated.rpt'
bin_file = '/Users/jonjones/temp/updated.bin'

namespace = {}; exec(open('/Users/jonjones/temp/my_dict.txt').read(), namespace); mapping = namespace['mapping']

enData = en.ENepanet()

enData.ENopen(inp_file, rpt_file, bin_file)

# --- Initialize hydraulics ---
enData.ENopenH()
enData.ENinitH(0)

t = 0

while t < model_time * 3600:
    t = enData.ENrunH()
    tstep = enData.ENnextH()

    if tstep <= 0:
        break

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



for sequence in sequences:
    operation_model = enData.copy()
    print(f"[DEBUG] Processing sequence: {sequence['name']}")
    for operation in sequence["operations"]:

        updated_inp = f"/Users/jonjones/temp/{sequence['name']}_{operation['name']}.inp"

        valves_to_close = operation.get("close_valves", []) or []
        valves_to_open = operation.get("open_valves", []) or []
        hydrants_to_open = operation.get("open_hydrants", []) or []

        orifice_size = operation.get("orifice_size", None)

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

            print(results_df.head())

    operation_model.ENcloseH()
    operation_model.ENclose()

enData.ENcloseH()
enData.ENclose()
    
    
    