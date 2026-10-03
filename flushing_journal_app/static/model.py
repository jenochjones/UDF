import wntr


def close_and_open_model_pipes(model: wntr.network.WaterNetworkModel, pipes_to_close: list[str], pipes_to_open: list[str]) -> None:
    """
    Close and open pipes in a water network model.

    Args:
        model (wntr.network.WaterNetworkModel): The water network model.
        pipes_to_close (list[str]): List of pipe names to close.
        pipes_to_open (list[str]): List of pipe names to open.

    Returns:
        None
    """
    for pipe_name in pipes_to_close:
        if pipe_name in model.pipe_name_list:
            model.get_link(pipe_name).status = "CLOSED"
            print(f"[DEBUG] Closed pipe: {pipe_name}")
        else:
            print(f"[WARNING] Pipe {pipe_name} not found in the model.")

    # Open the pipes after closing them
    for pipe_name in pipes_to_open:
        if pipe_name in model.pipe_name_list:
            model.get_link(pipe_name).status = "OPEN"
            print(f"[DEBUG] Opened pipe: {pipe_name}")

    return model