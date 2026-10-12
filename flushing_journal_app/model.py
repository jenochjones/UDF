import wntr

import pandas as pd


def run_water_network_model(model_store: dict, sequences: list) -> dict:
    """
    Run the water network model using the provided model store.

    Args:
        model_store (dict): A dictionary containing the water network model and other relevant data.
        sequences (list): A list of sequences to be processed.

    Returns:
        dict: The updated model store after running the model.
    """

    inp_file = model_store.get("inp_path")

    mapping = model_store.get("element_mapping", {})

    results_dict = {}

    namespace = {}; exec(open('./my_dict.txt').read(), namespace); mapping = namespace['mapping']

    #wn = wntr.network.io.read_inpfile(inp_file)

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

                seq_velocity = seq_results.link['velocity'].transpose() * 3.28084
                seq_velocity.columns = ['velocity']
                

                results_df = seq_velocity[seq_velocity['velocity'] > 5]
                comp_df = base_velocity.loc[base_velocity.index.intersection(results_df.index)]
                
                vel_dif = results_df / comp_df
                
                results_dict[sequence['name']][operation['name']] = vel_dif
                
                for hydrant in hydrants_to_open:
                    if hydrant in mapping:
                        junct_id = mapping['hydrants'][hydrant]
                        junct = seq_wn.get_node(junct_id)
                        junct.emmitter_coefficient = emitter_coefficient
        

        
