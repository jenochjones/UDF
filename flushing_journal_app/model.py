from wntr.epanet import toolkit as en

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

    model_time = model_store.get("model_time", 0)  # Default to 24 hours if not specified

    inp_file = model_store.get("inp_path")
    rpt_file = model_store.get("rpt_path")
    bin_file = model_store.get("bin_path")

    mapping = model_store.get("element_mapping", {})

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

    #base_results_df.to_csv('/Users/jonjones/temp/base_results.csv', index=False)

    with open('/Users/jonjones/temp/my_dict.txt', 'w') as f: f.write(f"mapping = {repr(mapping)}")

    enData.ENsaveinpfile('/Users/jonjones/temp/updated.inp')
    enData.ENcloseH()
    enData.ENclose()
    '''
    for sequence in sequences:
        operation_model = enData.copy()
        print(f"[DEBUG] Processing sequence: {sequence['name']}")
        for operation in sequence["operations"]:

            updated_inp = f"{sequence['name']}_{operation['name']}.inp"

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

                n_links = operation_model.ENgetcount(operation_model.EN_LINKCOUNT)

                results = []

                for i in range(1, n_links + 1):

                    link_id = operation_model.ENgetlinkid(i)
                    link_type = operation_model.ENgetlinktype(i)

                    # Link type 1 = Pipe
                    if link_type == operation_model.EN_PIPE:

                        velocity = operation_model.ENgetlinkvalue(i, operation_model.EN_VELOCITY)
                        flow = operation_model.ENgetlinkvalue(i, operation_model.EN_FLOW)

                        results.append({
                            "PipeID": link_id,
                            "Velocity": velocity,
                            "Flow": flow
                        })

                results_df = pd.DataFrame(results)

                print(results_df.head())

        operation_model.ENcloseH()
        operation_model.ENclose()

    enData.ENcloseH()
    enData.ENclose()
    '''

        
