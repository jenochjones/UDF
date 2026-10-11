# -*- coding: utf-8 -*-
"""
Created on Fri Aug  7 09:27:09 2026

@author: ejones
"""

def connect_hydrants(inp_file_path, shapefile_path, model_crs=None, hydrant_id_field=None):
    """
    Connect each hydrant in a shapefile to the nearest pipe in a WNTR model.

    Parameters
    ----------
    inp_file_path : str
        Path to the EPANET INP file.

    shapefile_path : str
        Path to the hydrant shapefile.

    model_crs : str, optional
        CRS of the water model coordinates, for example 3566 or "EPSG:3566".
        If None, the hydrant shapefile CRS is assumed to match the model coordinates.

    hydrant_id_field : str, optional
        Field in the hydrant shapefile to use as the hydrant junction name.
        If None, generated names are used.

    Returns
    -------
    wn : wntr.network.WaterNetworkModel or None
        Updated WNTR model if successful. None if an exception occurs.
    """

    try:
        import uuid
        import traceback
        import geopandas as gpd
        import wntr

        from shapely.geometry import Point, LineString

        # ---------------------------------------------------------------------
        # Helper functions
        # ---------------------------------------------------------------------
        def make_unique_pipe_name(base_pipe_name, wn_model):
            """
            Create a unique pipe name using the original base pipe name.

            This prevents names like:
                PipeA_abc123_def456

            and instead creates:
                PipeA_def456
            """
            while True:
                new_name = f"{base_pipe_name}_{uuid.uuid4().hex[:6]}"

                if new_name not in wn_model.link_name_list:
                    return new_name

        def make_unique_node_name(base_node_name, wn_model):
            """
            Create a unique node name if the proposed node already exists.
            """
            if base_node_name not in wn_model.node_name_list:
                return base_node_name

            while True:
                new_name = f"{base_node_name}_{uuid.uuid4().hex[:6]}"

                if new_name not in wn_model.node_name_list:
                    return new_name

        def make_unique_link_name(base_link_name, wn_model):
            """
            Create a unique link name if the proposed link already exists.
            """
            if base_link_name not in wn_model.link_name_list:
                return base_link_name

            while True:
                new_name = f"{base_link_name}_{uuid.uuid4().hex[:6]}"

                if new_name not in wn_model.link_name_list:
                    return new_name

        def build_pipe_geometries(wn_model):
            """
            Build pipe geometry list from the current WNTR model.
            """
            geometries = []

            for current_pipe_name, current_pipe in wn_model.pipes():
                current_start_node = wn_model.get_node(current_pipe.start_node_name)
                current_end_node = wn_model.get_node(current_pipe.end_node_name)

                current_start_coords = getattr(current_start_node, "coordinates", None)
                current_end_coords = getattr(current_end_node, "coordinates", None)

                if current_start_coords is None or current_end_coords is None:
                    continue

                coords = [current_start_coords]

                # WNTR pipes may have intermediate vertices.
                vertices = getattr(current_pipe, "vertices", None)
                if vertices:
                    coords.extend(vertices)

                coords.append(current_end_coords)

                if len(coords) >= 2:
                    geometries.append({
                        "name": current_pipe_name,
                        "geometry": LineString(coords)
                    })

            return geometries

        # ---------------------------------------------------------------------
        # Load WNTR model from INP file
        # ---------------------------------------------------------------------
        wn = wntr.network.WaterNetworkModel(inp_file_path)

        # ---------------------------------------------------------------------
        # Track original base pipe names
        # ---------------------------------------------------------------------
        # Key:
        #   Current pipe name in the model
        #
        # Value:
        #   Original base pipe name to use when creating future split pipes
        #
        # Example:
        #   pipe_base_names["P-100"] = "P-100"
        #   pipe_base_names["P-100_a1b2c3"] = "P-100"
        #
        # If P-100_a1b2c3 is split later, the new pipe becomes:
        #   P-100_d4e5f6
        #
        # Not:
        #   P-100_a1b2c3_d4e5f6
        pipe_base_names = {}

        for pipe_name, _ in wn.pipes():
            pipe_base_names[pipe_name] = pipe_name

        # ---------------------------------------------------------------------
        # Load hydrant shapefile
        # ---------------------------------------------------------------------
        hydrants_gdf = gpd.read_file(shapefile_path)

        if hydrants_gdf.empty:
            print("The hydrant shapefile does not contain any features.")
            return None

        # Normalize EPSG input if user passes an integer like 3566.
        if isinstance(model_crs, int):
            model_crs = f"EPSG:{model_crs}"

        if hydrants_gdf.crs is None and model_crs is not None:
            hydrants_gdf = hydrants_gdf.set_crs(model_crs)

        if model_crs is not None and hydrants_gdf.crs is not None:
            hydrants_gdf = hydrants_gdf.to_crs(model_crs)

        # If model_crs is not provided, assume the shapefile coordinates already
        # match the model coordinates.
        if model_crs is None:
            model_crs = hydrants_gdf.crs

        # ---------------------------------------------------------------------
        # Build pipe geometry from WNTR model
        # ---------------------------------------------------------------------
        pipe_geometries = build_pipe_geometries(wn)

        if not pipe_geometries:
            print("No pipe geometry could be built from the INP model.")
            return None

        # ---------------------------------------------------------------------
        # Connect each hydrant
        # ---------------------------------------------------------------------
        connected_count = 0
        skipped_count = 0

        for _, hydrant_row in hydrants_gdf.iterrows():
            hydrant_geom = hydrant_row.geometry

            if hydrant_geom is None or hydrant_geom.is_empty:
                skipped_count += 1
                continue

            # Use point geometry directly. For non-point features, use centroid.
            if hydrant_geom.geom_type == "Point":
                hydrant_point = hydrant_geom
            else:
                hydrant_point = hydrant_geom.centroid

            # -----------------------------------------------------------------
            # Determine hydrant junction name
            # -----------------------------------------------------------------
            if hydrant_id_field and hydrant_id_field in hydrant_row:
                raw_id = hydrant_row[hydrant_id_field]

                if raw_id is not None and str(raw_id).strip() != "":
                    hydrant_junction_name = str(raw_id).strip()
                else:
                    hydrant_junction_name = None
            else:
                hydrant_junction_name = None

            if not hydrant_junction_name:
                hydrant_junction_name = f"HYDRANT_{uuid.uuid4().hex[:8]}"

            hydrant_junction_name = make_unique_node_name(hydrant_junction_name, wn)

            # -----------------------------------------------------------------
            # Find nearest pipe
            # -----------------------------------------------------------------
            nearest_pipe = min(
                pipe_geometries,
                key=lambda item: hydrant_point.distance(item["geometry"])
            )

            pipe_name = nearest_pipe["name"]
            pipe_line = nearest_pipe["geometry"]
            pipe = wn.get_link(pipe_name)

            if pipe is None:
                skipped_count += 1
                continue

            nearest_point = pipe_line.interpolate(pipe_line.project(hydrant_point))

            x_hyd, y_hyd = hydrant_point.x, hydrant_point.y
            x_split, y_split = nearest_point.x, nearest_point.y

            start_node_name = pipe.start_node_name
            end_node_name = pipe.end_node_name

            start_node = wn.get_node(start_node_name)
            end_node = wn.get_node(end_node_name)

            start_coords = getattr(start_node, "coordinates", None)
            end_coords = getattr(end_node, "coordinates", None)

            if start_coords is None or end_coords is None:
                raise ValueError(
                    f"Pipe '{pipe_name}' does not have endpoint coordinates."
                )

            start_pt = Point(start_coords)
            end_pt = Point(end_coords)
            split_pt = Point(x_split, y_split)

            # -----------------------------------------------------------------
            # Determine whether to connect to endpoint or split pipe
            # -----------------------------------------------------------------
            tolerance = 1e-6

            if split_pt.distance(start_pt) < tolerance:
                connection_node_name = start_node_name
                connection_elevation = start_node.elevation

            elif split_pt.distance(end_pt) < tolerance:
                connection_node_name = end_node_name
                connection_elevation = end_node.elevation

            else:
                connection_node_name = f"{hydrant_junction_name}_CONN"
                connection_node_name = make_unique_node_name(connection_node_name, wn)

                # -------------------------------------------------------------
                # Important naming update
                # -------------------------------------------------------------
                # If the pipe being split is already a generated split pipe,
                # use its original base pipe name instead of appending another ID.
                #
                # Example:
                #   Current pipe being split: P-100_a1b2c3
                #   Original base pipe name:  P-100
                #   New pipe name:            P-100_d4e5f6
                #
                # This avoids:
                #   P-100_a1b2c3_d4e5f6
                # -------------------------------------------------------------
                base_pipe_name = pipe_base_names.get(pipe_name, pipe_name)
                new_pipe_name = make_unique_pipe_name(base_pipe_name, wn)

                # Use distance along actual pipe geometry, including vertices.
                split_distance = pipe_line.project(split_pt)

                if pipe_line.length <= 0:
                    skipped_count += 1
                    continue

                split_fraction = split_distance / pipe_line.length

                # Keep split fraction away from exact 0 or 1.
                split_fraction = max(0.000001, min(0.999999, split_fraction))

                print(
                    f"Splitting pipe '{pipe_name}' at "
                    f"{split_fraction:.4f} fraction of its length. "
                    f"New pipe name: '{new_pipe_name}'."
                )

                wn = wntr.morph.split_pipe(
                    wn,
                    pipe_name_to_split=pipe_name,
                    new_pipe_name=new_pipe_name,
                    new_junction_name=connection_node_name,
                    split_at_point=split_fraction
                )

                # Preserve the original base pipe name for both resulting pipes.
                # The original pipe keeps its existing name in WNTR.
                # The newly created pipe gets the clean base plus a fresh UUID.
                pipe_base_names[pipe_name] = base_pipe_name
                pipe_base_names[new_pipe_name] = base_pipe_name

                connection_node = wn.get_node(connection_node_name)
                connection_node.coordinates = (x_split, y_split)

                # Interpolate elevation between pipe endpoints.
                start_elev = start_node.elevation
                end_elev = end_node.elevation
                connection_elevation = start_elev + split_fraction * (end_elev - start_elev)
                connection_node.elevation = connection_elevation

                # Refresh pipe geometry list because the model topology changed.
                pipe_geometries = build_pipe_geometries(wn)

                # Make sure any newly discovered pipe names are represented.
                for refreshed_pipe_name, _ in wn.pipes():
                    if refreshed_pipe_name not in pipe_base_names:
                        pipe_base_names[refreshed_pipe_name] = refreshed_pipe_name

            # -----------------------------------------------------------------
            # Add hydrant junction
            # -----------------------------------------------------------------
            if hydrant_junction_name not in wn.node_name_list:
                wn.add_junction(
                    hydrant_junction_name,
                    base_demand=0.0,
                    elevation=connection_elevation,
                    coordinates=(x_hyd, y_hyd)
                )

            # -----------------------------------------------------------------
            # Add pipe from hydrant to connection node
            # -----------------------------------------------------------------
            hydrant_pipe_base_name = f"{hydrant_junction_name}_pipe"
            hydrant_pipe_name = make_unique_link_name(
                f"{hydrant_pipe_base_name}_{uuid.uuid4().hex[:6]}",
                wn
            )

            hydrant_pipe_length = float(split_pt.distance(Point(x_hyd, y_hyd)))

            if hydrant_pipe_length <= 0:
                hydrant_pipe_length = 0.01

            wn.add_pipe(
                hydrant_pipe_name,
                hydrant_junction_name,
                connection_node_name,
                length=hydrant_pipe_length,
                diameter=0.1524,
                roughness=100.0,
                minor_loss=0.0,
                initial_status="OPEN"
            )

            connected_count += 1

        print(f"Hydrants connected: {connected_count}")
        print(f"Hydrants skipped: {skipped_count}")

        wntr.network.write_inpfile(wn, inp_file_path)

        return wn

    except Exception:
        print(traceback.format_exc())
        return None
    
    
    
results = connect_hydrants(r"C:\WebApps\test files\MapletonDWModel_EX_2025_For_UDF_Copy.inp", r"C:\WebApps\test files\hydrants.shp", model_crs=3566, hydrant_id_field="ASSETID")