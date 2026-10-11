#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Oct 11 08:51:27 2026

@author: jonjones
"""

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Sun Oct 11 07:40:04 2026

@author: jonjones
"""

import ctypes
from ctypes import byref

import wntr

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




#inp_file = r'C:\WebApps\UDF\flushing_journal_app\temp\updated.inp'
#rpt_file = r'C:\WebApps\UDF\flushing_journal_app\temp\updated.rpt'
#bin_file = r'C:\WebApps\UDF\flushing_journal_app\temp\updated.bin'

inp_file = '/Users/jonjones/Sites/UDF/flushing_journal_app/temp/updatedSS.inp'
rpt_file = '/Users/jonjones/Sites/UDF/flushing_journal_app/temp/updated.rpt'
bin_file = '/Users/jonjones/Sites/UDF/flushing_journal_app/temp/updated.bin'

results_dict = {}

namespace = {}; exec(open('/Users/jonjones/Sites/UDF/flushing_journal_app/temp/my_dict.txt').read(), namespace); mapping = namespace['mapping']

#wn = wntr.network.io.read_inpfile(inp_file)

wn = wntr.network.WaterNetworkModel(inp_file)

sim = wntr.sim.EpanetSimulator(wn)
results = sim.run_sim()

velocity = results.link['velocity']


    
    