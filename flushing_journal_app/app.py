from datetime import date, datetime
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from pyproj import CRS, Transformer
import wntr
import geopandas as gpd
import json
import math
import os
import re
import tempfile
import traceback
import uuid
import io
import pickle
import zipfile
from shapely.geometry import shape, Point, LineString


app = Flask(__name__)

# Spyder-friendly hard-coded settings
UPLOAD_FOLDER = os.path.join(tempfile.gettempdir(), "flushing_journal_uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Simple in-memory model storage.
# For a single-user local Flask app, this is usually fine.
# For production/multi-user deployment, use sessions, database storage,
# or a server-side cache keyed by user/session ID.
MODEL_STORE = {
    "wn": None,
    "inp_path": None,
    "model_crs": None,
    "pipe_geojson": None,
    "uploaded_layers": {
        "valves": None,
        "hydrants": None
    },
    "sequences": [],
    "snapshots": {}
}


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/upload_model", methods=["POST"])
def upload_model():
    """
    Upload an EPANET INP file, load it into WNTR, store it for later use,
    convert pipes to GeoJSON, and return the GeoJSON to the browser.
    """

    try:
        if "inp_file" not in request.files:
            return jsonify({
                "success": False,
                "message": "No inp_file was included in the request."
            }), 400

        inp_file = request.files["inp_file"]
        model_crs = request.form.get("model_crs", "").strip()
        if model_crs and not model_crs.upper().startswith("EPSG:"):
            model_crs = f"EPSG:{model_crs}"

        if inp_file.filename == "":
            return jsonify({
                "success": False,
                "message": "No file was selected."
            }), 400

        if not model_crs:
            return jsonify({
                "success": False,
                "message": "Model CRS is required. Example: EPSG:26912"
            }), 400

        filename = secure_filename(inp_file.filename)

        if not filename.lower().endswith(".inp"):
            return jsonify({
                "success": False,
                "message": "The selected file must be an EPANET .inp file."
            }), 400

        inp_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        inp_file.save(inp_path)

        # Load the EPANET model into WNTR and store it for later use.
        wn = wntr.network.WaterNetworkModel(inp_path)

        pipe_geojson = water_network_pipes_to_geojson(
            wn=wn,
            model_crs=model_crs
        )

        # If a model_timestep was supplied, attempt to run the simulation up to that hour
        model_timestep = 0.0
        try:
            mt_str = request.form.get('model_timestep', '').strip()
            if mt_str:
                model_timestep = float(mt_str)
        except Exception:
            model_timestep = 0.0

        snapshot_saved = False
        snapshot_id = None
        snapshot_message = None

        if model_timestep and model_timestep > 0:
            try:
                # Set duration to the requested timestep (in seconds)
                duration_seconds = int(max(0, min(23.75, model_timestep)) * 3600)
                wn.options.time.duration = duration_seconds

                # Run the simulator (WNTR pure Python simulator)
                sim = wntr.sim.WNTRSimulator(wn)
                results = sim.run_sim()

                # Save a pickled snapshot of the model and results so it can be reused later
                snapshot_key = f"{model_timestep:.2f}h"
                snapshot_obj = {
                    'model_timestep_hours': model_timestep,
                    'wn_pickle': pickle.dumps(wn),
                    'results_pickle': pickle.dumps(results)
                }
                MODEL_STORE['snapshots'][snapshot_key] = snapshot_obj
                snapshot_saved = True
                snapshot_id = snapshot_key
                # Optionally write an inp file snapshot for debugging/inspection
                try:
                    snapshot_inp = os.path.join(app.config['UPLOAD_FOLDER'], f"{secure_filename(filename)}.snapshot_{int(model_timestep*100)}.inp")
                    wntr.network.write_inpfile(wn, snapshot_inp)
                except Exception:
                    pass
            except Exception as run_exc:
                snapshot_message = f"Model run to {model_timestep} h failed: {str(run_exc)}"
                print(traceback.format_exc())

        print(f"[DEBUG] Model CRS: {model_crs}")

        MODEL_STORE["wn"] = wn
        MODEL_STORE["inp_path"] = inp_path
        MODEL_STORE["model_crs"] = model_crs
        MODEL_STORE["pipe_geojson"] = pipe_geojson
        response = {
            "success": True,
            "message": "Model loaded successfully.",
            "model_crs": model_crs,
            "pipe_count": len(pipe_geojson.get("features", [])),
            "pipe_geojson": pipe_geojson
        }

        if snapshot_saved:
            response['model_timestep'] = model_timestep
            response['snapshot_id'] = snapshot_id
            response['snapshot_message'] = snapshot_message or f"Snapshot saved at {model_timestep} h"
        elif snapshot_message:
            response['model_timestep'] = model_timestep
            response['snapshot_message'] = snapshot_message

        return jsonify(response)

    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


@app.route("/model_pipes", methods=["GET"])
def model_pipes():
    """
    Optional endpoint to retrieve the currently loaded pipe GeoJSON later.
    """

    if MODEL_STORE["pipe_geojson"] is None:
        return jsonify({
            "success": False,
            "message": "No model has been loaded yet."
        }), 404

    return jsonify({
        "success": True,
        "pipe_geojson": MODEL_STORE["pipe_geojson"]
    })


@app.route("/download_project", methods=["GET"])
def download_project():
    try:
        return send_project_archive()
    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


@app.route("/upload_project", methods=["POST"])
def upload_project():
    try:
        result = restore_project_request(request.files)

        return jsonify({
            "success": True,
            "message": "Project loaded successfully.",
            "model_crs": result["model_crs"],
            "pipe_geojson": result["pipe_geojson"],
            "hydrants": result["hydrants"],
            "valves": result["valves"],
            "sequences": result.get("sequences", [])
        })
    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


@app.route("/connect_hydrants", methods=["POST"])
def connect_hydrants():

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

    # Connect each uploaded hydrant to the nearest pipe in the loaded WNTR model.
    try:
        if MODEL_STORE["wn"] is None:
            return jsonify({
                "success": False,
                "message": "No model has been loaded yet."
            }), 400

        hydrants_layer = MODEL_STORE["uploaded_layers"].get("hydrants")
        if not hydrants_layer or not hydrants_layer["geojson"].get("features"):
            return jsonify({
                "success": False,
                "message": "No hydrants shapefile has been uploaded."
            }), 400

        if MODEL_STORE["pipe_geojson"] is None:
            return jsonify({
                "success": False,
                "message": "No model pipe geometry is available."
            }), 400

        wn = MODEL_STORE["wn"]
        model_crs = MODEL_STORE["model_crs"]
        hydrant_features = hydrants_layer["geojson"]["features"]
        pipe_base_names = {}

        def normalize_crs(crs_str):
            if crs_str is None:
                return None
            crs_text = str(crs_str).strip()
            crs_text = crs_text.upper()
            if not crs_text.startswith("EPSG:"):
                crs_text = f"EPSG:{crs_text}"
            return crs_text

        model_crs = normalize_crs(model_crs)
        pipe_geometries = build_pipe_geometries(wn)

        if not pipe_geometries:
            return jsonify({
                "success": False,
                "message": "The loaded model contains no pipe geometries."
            }), 400

        transformer_to_model = Transformer.from_crs(
            "EPSG:4326",
            model_crs,
            always_xy=True
        )

        hydrant_id_field = hydrants_layer.get("id_field")
        connected_count = 0
        skipped_count = 0

        for hydrant_feature in hydrant_features:
            geometry = hydrant_feature.get("geometry")
            if not geometry:
                skipped_count += 1
                continue

            hydrant_geom_4326 = shape(geometry)
            if hydrant_geom_4326.is_empty:
                skipped_count += 1
                continue

            if hydrant_geom_4326.geom_type == "Point":
                hydrant_point_4326 = hydrant_geom_4326
            else:
                hydrant_point_4326 = hydrant_geom_4326.centroid

            x_hyd, y_hyd = transformer_to_model.transform(
                hydrant_point_4326.x,
                hydrant_point_4326.y
            )
            hydrant_point = Point(x_hyd, y_hyd)

            if hydrant_point.is_empty:
                skipped_count += 1
                continue

            properties = hydrant_feature.get("properties", {}) or {}
            hydrant_junction_name = None
            if hydrant_id_field and hydrant_id_field in properties:
                raw_id = properties.get(hydrant_id_field)
                if raw_id is not None and str(raw_id).strip() != "":
                    hydrant_junction_name = str(raw_id).strip()

            if not hydrant_junction_name:
                hydrant_junction_name = f"HYDRANT_{uuid.uuid4().hex[:8]}"

            hydrant_junction_name = make_unique_node_name(hydrant_junction_name, wn)

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

                base_pipe_name = pipe_base_names.get(pipe_name, pipe_name)
                new_pipe_name = make_unique_pipe_name(base_pipe_name, wn)

                split_distance = pipe_line.project(split_pt)
                if pipe_line.length <= 0:
                    skipped_count += 1
                    continue

                split_fraction = split_distance / pipe_line.length
                split_fraction = max(0.000001, min(0.999999, split_fraction))

                wn = wntr.morph.split_pipe(
                    wn,
                    pipe_name_to_split=pipe_name,
                    new_pipe_name=new_pipe_name,
                    new_junction_name=connection_node_name,
                    split_at_point=split_fraction
                )

                pipe_base_names[pipe_name] = base_pipe_name
                pipe_base_names[new_pipe_name] = base_pipe_name

                connection_node = wn.get_node(connection_node_name)
                connection_node.coordinates = (x_split, y_split)

                start_elev = start_node.elevation
                end_elev = end_node.elevation
                connection_elevation = start_elev + split_fraction * (end_elev - start_elev)
                connection_node.elevation = connection_elevation

                pipe_geometries = build_pipe_geometries(wn)
                for refreshed_pipe_name, _ in wn.pipes():
                    if refreshed_pipe_name not in pipe_base_names:
                        pipe_base_names[refreshed_pipe_name] = refreshed_pipe_name

            if hydrant_junction_name not in wn.node_name_list:
                wn.add_junction(
                    hydrant_junction_name,
                    base_demand=0.0,
                    elevation=connection_elevation,
                    coordinates=(x_hyd, y_hyd)
                )

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

        MODEL_STORE["pipe_geojson"] = water_network_pipes_to_geojson(
            wn=wn,
            model_crs=model_crs
        )
        
        MODEL_STORE["wn"] = wn

        if MODEL_STORE["inp_path"]:
            wntr.network.write_inpfile(wn, MODEL_STORE["inp_path"])

        return jsonify({
            "success": True,
            "message": "Hydrants have been connected to the model.",
            "connected_count": connected_count,
            "skipped_count": skipped_count,
            "pipe_geojson": MODEL_STORE["pipe_geojson"]
        })
    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


@app.route("/snap_valves", methods=["POST"])
def snap_valves():
    try:
        if MODEL_STORE["pipe_geojson"] is None:
            return jsonify({"success": False, "message": "No model has been loaded yet."}), 400

        valves_layer = MODEL_STORE["uploaded_layers"].get("valves")
        if not valves_layer or not valves_layer.get("geojson") or not valves_layer["geojson"].get("features"):
            return jsonify({"success": False, "message": "No valves shapefile has been uploaded."}), 400

        pipe_features = [feature for feature in MODEL_STORE["pipe_geojson"].get("features", []) if feature.get("geometry")]
        if not pipe_features:
            return jsonify({"success": False, "message": "The loaded model does not contain any pipe geometries."}), 400

        features = valves_layer["geojson"].get("features", [])
        for feature in features:
            geometry = feature.get("geometry")
            if not geometry:
                continue

            point = shape(geometry)
            best_distance = None
            best_location = None

            for pipe_feature in pipe_features:
                try:
                    pipe_geometry = shape(pipe_feature.get("geometry"))
                except Exception:
                    continue

                if not pipe_geometry.is_valid:
                    continue

                distance = point.distance(pipe_geometry)
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_location = pipe_geometry.interpolate(pipe_geometry.project(point))

            if best_location is not None:
                feature["geometry"]["coordinates"] = [best_location.x, best_location.y]

        MODEL_STORE["uploaded_layers"]["valves"]["geojson"]["features"] = features

        save_dir = MODEL_STORE["uploaded_layers"]["valves"].get("path")
        shape_name = MODEL_STORE["uploaded_layers"]["valves"].get("shape_name")
        if save_dir and shape_name:
            try:
                write_point_geojson_to_shapefile(save_dir, shape_name, {"type": "FeatureCollection", "features": features}, crs="EPSG:4326")
            except Exception as e:
                print("Warning: failed to write snapped valves shapefile back to disk:", e)

        return jsonify({"success": True, "message": "Valves snapped to the closest pipes.", "geojson": {"type": "FeatureCollection", "features": features}})
    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/set_layer_id_field", methods=["POST"])
def set_layer_id_field():
    try:
        data = request.get_json(silent=True) or {}
        layer_type = data.get("layer_type", "").strip().lower()
        id_field = data.get("id_field", "").strip()

        if layer_type not in {"valves", "hydrants"}:
            return jsonify({
                "success": False,
                "message": "Layer type must be valves or hydrants."
            }), 400

        layer = MODEL_STORE["uploaded_layers"].get(layer_type)
        if not layer or not layer.get("geojson"):
            return jsonify({
                "success": False,
                "message": "No layer has been uploaded for that type."
            }), 400

        if not id_field:
            return jsonify({
                "success": False,
                "message": "An ID field must be provided."
            }), 400

        if id_field not in layer.get("fields", []):
            return jsonify({
                "success": False,
                "message": "Selected ID field is not available in the uploaded layer."
            }), 400

        layer["id_field"] = id_field

        return jsonify({
            "success": True,
            "message": "Layer ID field saved.",
            "layer_type": layer_type,
            "selected_id_field": id_field
        })

    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


@app.route("/update_feature_geometry", methods=["POST"])
def update_feature_geometry():
    """
    Receive an updated feature GeoJSON for a given uploaded layer (hydrants or valves)
    and update the stored in-memory GeoJSON. If the original shapefile exists on
    disk, attempt to overwrite it with the updated GeoJSON so exported ZIPs include
    the new coordinates.
    """

    try:
        data = request.get_json(silent=True) or {}
        layer_type = (data.get("layer_type") or "").strip().lower()
        id_field = data.get("id_field") or None
        id_value = data.get("id_value") or None
        feature = data.get("feature")

        if layer_type not in {"hydrants", "valves"}:
            return jsonify({"success": False, "message": "Layer type must be hydrants or valves."}), 400

        if not feature or not isinstance(feature, dict) or not feature.get("geometry"):
            return jsonify({"success": False, "message": "A feature with geometry must be provided."}), 400

        layer = MODEL_STORE["uploaded_layers"].get(layer_type)
        if not layer or not layer.get("geojson"):
            return jsonify({"success": False, "message": "No uploaded layer found for that type."}), 400

        features = layer["geojson"].get("features", [])

        # Try to find by id_field if provided
        matched_index = None
        if id_field and id_value is not None:
            for idx, f in enumerate(features):
                props = f.get("properties") or {}
                if str(props.get(id_field)) == str(id_value):
                    matched_index = idx
                    break

        # Fallback: try matching 'id' or 'ID' or 'name' property
        if matched_index is None:
            for key in ("id", "ID", "name", "Name"):
                for idx, f in enumerate(features):
                    props = f.get("properties") or {}
                    if key in props and feature.get("properties") and props.get(key) == feature.get("properties").get(key):
                        matched_index = idx
                        break
                if matched_index is not None:
                    break

        # Final fallback: match by nearest coordinate if geometry present
        if matched_index is None:
            try:
                incoming_geom = shape(feature.get("geometry"))
                best_idx = None
                best_dist = None
                for idx, f in enumerate(features):
                    g = f.get("geometry")
                    if not g:
                        continue
                    try:
                        existing_geom = shape(g)
                    except Exception:
                        continue
                    # use simple distance on lon/lat geometry
                    dist = incoming_geom.distance(existing_geom)
                    if best_dist is None or dist < best_dist:
                        best_idx = idx
                        best_dist = dist
                matched_index = best_idx
            except Exception:
                matched_index = None

        if matched_index is None:
            return jsonify({"success": False, "message": "Could not locate matching feature to update."}), 404

        # Replace geometry (and optionally properties) for the matched feature
        features[matched_index]["geometry"] = feature.get("geometry")
        # Optionally update properties if provided
        if feature.get("properties"):
            features[matched_index]["properties"] = feature.get("properties")

        # Write back into model store
        MODEL_STORE["uploaded_layers"][layer_type]["geojson"]["features"] = features

        # If shapefile exists on disk, attempt to overwrite it with updated geojson
        save_dir = MODEL_STORE["uploaded_layers"][layer_type].get("path")
        shape_name = MODEL_STORE["uploaded_layers"][layer_type].get("shape_name")
        if save_dir and shape_name:
            try:
                write_point_geojson_to_shapefile(save_dir, shape_name, {"type": "FeatureCollection", "features": features}, crs="EPSG:4326")
            except Exception as e:
                print("Warning: failed to write shapefile back to disk:", e)

        return jsonify({"success": True, "message": "Feature geometry updated."})

    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/upload_shapefile", methods=["POST"])
def upload_shapefile():
    """
    Upload a point shapefile set for valves or hydrants, convert it to GeoJSON,
    store it in memory for later use, and return it to the browser.
    """

    try:
        layer_type = request.form.get("layer_type", "").strip().lower()

        if layer_type not in {"valves", "hydrants"}:
            return jsonify({
                "success": False,
                "message": "Layer type must be either valves or hydrants."
            }), 400

        uploaded_files = request.files.getlist("shape_files")
        if not uploaded_files or all(file.filename == "" for file in uploaded_files):
            return jsonify({
                "success": False,
                "message": "No shapefile files were provided."
            }), 400

        shp_file = None
        save_dir = os.path.join(
            app.config["UPLOAD_FOLDER"],
            f"{layer_type}_{uuid.uuid4().hex[:8]}"
        )
        os.makedirs(save_dir, exist_ok=True)

        for uploaded_file in uploaded_files:
            if uploaded_file.filename == "":
                continue

            filename = secure_filename(uploaded_file.filename)
            uploaded_file.save(os.path.join(save_dir, filename))

            if filename.lower().endswith(".shp"):
                shp_file = filename

        if not shp_file:
            return jsonify({
                "success": False,
                "message": "A .shp file is required for upload."
            }), 400

        source_crs_value = request.form.get("source_crs", "").strip()
        selected_id_field = request.form.get("id_field", "").strip() or None
        shp_path = os.path.join(save_dir, shp_file)
        
        geojson, field_names = point_shapefile_to_geojson(
            shp_path=shp_path,
            source_crs=source_crs_value or None
        )

        if selected_id_field and selected_id_field not in field_names:
            selected_id_field = None

        if layer_type == "valves":
            for feature in geojson.get("features", []):
                props = feature.setdefault("properties", {})
                if "original_location" not in props and feature.get("geometry"):
                    coords = feature["geometry"].get("coordinates")
                    if isinstance(coords, list) and len(coords) >= 2:
                        props["original_location"] = [coords[0], coords[1]]

        MODEL_STORE["uploaded_layers"][layer_type] = {
            "path": save_dir,
            "geojson": geojson,
            "shape_name": shp_file,
            "fields": field_names,
            "id_field": selected_id_field
        }
        print('Done')

        return jsonify({
            "success": True,
            "message": f"{layer_type.title()} shapefile loaded successfully.",
            "layer_type": layer_type,
            "feature_count": len(geojson.get("features", [])),
            "geojson": geojson,
            "field_names": field_names,
            "selected_id_field": selected_id_field
        })

    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


@app.route("/upload_sequences", methods=["POST"])
def upload_sequences():
    """
    Upload one or more sequence text files, parse them on the backend,
    store the sequence array, and return it to the frontend.
    """
    try:
        uploaded_files = request.files.getlist("sequence_files")
        if not uploaded_files or all(file.filename == "" for file in uploaded_files):
            return jsonify({
                "success": False,
                "message": "No sequence files were provided."
            }), 400

        sequences = []
        for uploaded_file in uploaded_files:
            if uploaded_file.filename == "":
                continue

            filename = secure_filename(uploaded_file.filename)
            if not filename.lower().endswith(".txt"):
                return jsonify({
                    "success": False,
                    "message": "Only .txt sequence files are supported."
                }), 400

            text = uploaded_file.stream.read().decode("utf-8", errors="replace")
            sequence = parse_sequence_text(text, filename)
            sequences.append(sequence)

        MODEL_STORE["sequences"] = sequences

        return jsonify({
            "success": True,
            "message": f"Loaded {len(sequences)} sequence file(s).",
            "sequences": sequences
        })
    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


@app.route("/save_sequences", methods=["POST"])
def save_sequences():
    try:
        data = request.get_json(silent=True) or {}
        sequences = data.get("sequences")

        if sequences is None:
            return jsonify({
                "success": False,
                "message": "No sequences were provided."
            }), 400

        if not isinstance(sequences, list):
            return jsonify({
                "success": False,
                "message": "Sequences must be an array."
            }), 400

        MODEL_STORE["sequences"] = sequences

        return jsonify({
            "success": True,
            "message": "Sequences saved."
        })
    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({
            "success": False,
            "message": str(exc)
        }), 500


def receive_sequence_run_request(expected_count=None):
    data = request.get_json(silent=True) or {}
    sequences = data.get("sequences")

    if not isinstance(sequences, list):
        return None, (jsonify({
            "success": False,
            "message": "Sequences must be an array."
        }), 400)

    if not sequences:
        return None, (jsonify({
            "success": False,
            "message": "At least one sequence is required."
        }), 400)

    if expected_count is not None and len(sequences) != expected_count:
        return None, (jsonify({
            "success": False,
            "message": f"Exactly {expected_count} sequence is required."
        }), 400)

    for sequence in sequences:
        if not isinstance(sequence, dict) or not isinstance(sequence.get("operations"), list):
            return None, (jsonify({
                "success": False,
                "message": "Each sequence must include an operations array."
            }), 400)

    return sequences, None


@app.route("/run_sequences", methods=["POST"])
def run_sequences():
    sequences, error = receive_sequence_run_request()
    if error:
        return error

    MODEL_STORE["sequences"] = sequences
    return jsonify({
        "success": True,
        "message": f"Received {len(sequences)} sequence(s) for processing.",
        "sequences": sequences
    })


@app.route("/run_sequence", methods=["POST"])
def run_sequence():
    sequences, error = receive_sequence_run_request(expected_count=1)
    if error:
        return error

    MODEL_STORE["sequences"] = sequences
    return jsonify({
        "success": True,
        "message": "Received the current sequence for processing.",
        "sequences": sequences
    })


def parse_sequence_text(text, filename=None):
    sequence = {
        "name": filename[:-4] if filename and filename.lower().endswith(".txt") else (filename or "Sequence"),
        "operations": []
    }

    if text is None:
        return sequence

    cleaned_text = text.strip()
    name_match = re.search(r"\[([^\]]+)\]", cleaned_text)
    if name_match:
        sequence["name"] = name_match.group(1).strip()

    operation_blocks = re.findall(r"\(\d+\)[\s\S]*?(?=(?:\(\d+\)|$))", cleaned_text)

    for block in operation_blocks:
        operation_match = re.match(r"^\((\d+)\)", block.strip())
        if not operation_match:
            continue

        operation_name = operation_match.group(1)
        open_valves = []
        close_valves = []
        open_hydrants = []
        orifice_size = ""
        target_velocity = ""
        map_message = ""

        open_valves_match = re.search(r">([^<>]*)<", block)
        if open_valves_match:
            open_valves = [val.strip() for val in open_valves_match.group(1).split(",") if val.strip()]

        close_valves_match = re.search(r"<([^<>]*)>", block)
        if close_valves_match:
            close_valves = [val.strip() for val in close_valves_match.group(1).split(",") if val.strip()]

        hydrants_match = re.search(r"\{([^}]*)\}", block)
        if hydrants_match:
            hydrants_value = hydrants_match.group(1).strip()
            if hydrants_value:
                parts = hydrants_value.split("*", 1)
                hydrants_part = parts[0].strip()
                if hydrants_part:
                    open_hydrants = [val.strip() for val in hydrants_part.split(",") if val.strip()]
                if len(parts) > 1:
                    orifice_size = parts[1].strip()

        map_message_match = re.search(r"\|([^|]*)\|", block)
        if map_message_match:
            map_message = map_message_match.group(1).strip()

        sequence["operations"].append({
            "name": operation_name,
            "open_valves": open_valves,
            "close_valves": close_valves,
            "open_hydrants": open_hydrants,
            "orifice_size": orifice_size,
            "target_velocity": target_velocity,
            "toggle_mode": "Orifice Size",
            "map_message": map_message
        })

    return sequence


def sequence_to_text(sequence):
    lines = []
    if sequence.get("name"):
        lines.append(f"[{sequence['name']}]".strip())
        lines.append("")

    for operation in sequence.get("operations", []):
        lines.append(f"({operation.get('name', '')})")

        open_valves_text = ",".join(operation.get("open_valves", []))
        lines.append(f">{open_valves_text}<")

        close_valves_text = ",".join(operation.get("close_valves", []))
        lines.append(f"<{close_valves_text}>")

        hydrants = ",".join(operation.get("open_hydrants", []))
        orifice_size = operation.get("orifice_size", "") or ""
        if hydrants or orifice_size:
            lines.append(f"{{{hydrants}{'*' + orifice_size if orifice_size else ''}}}")
        else:
            lines.append("{}")

        map_message = operation.get("map_message", "") or ""
        lines.append(f"|{map_message}|")
        lines.append("")

    return "\n".join(lines).strip() + "\n"


def sanitize_sequence_filename(name):
    sanitized = re.sub(r"[^a-zA-Z0-9._-]+", "_", name or "sequence")
    if not sanitized.lower().endswith(".txt"):
        sanitized = f"{sanitized}.txt"
    return sanitized


def point_shapefile_to_geojson(shp_path, source_crs=None):
    """
    Read a point shapefile and convert it to GeoJSON in EPSG:4326.
    """

    if not os.path.exists(shp_path):
        raise ValueError("Shapefile was not found on disk.")

    gdf = gpd.read_file(shp_path)
    
    print(f"[DEBUG] Current CRS: {gdf.crs}")
    print(f"[DEBUG] Source CRS provided: {source_crs}")
    print(f"[DEBUG] Sample coordinates before transformation: {gdf.geometry.iloc[0] if len(gdf) > 0 else 'No geometries'}")

    if gdf.empty:
        return {
            "type": "FeatureCollection",
            "features": []
        }, []

    geometry_types = {geom_type.lower() for geom_type in gdf.geom_type.unique()}
    if not geometry_types.issubset({"point", "multipoint"}):
        raise ValueError("Only point shapefiles are supported for this workflow.")

    # Normalize CRS strings for comparison
    def normalize_crs(crs_str):
        """Normalize CRS string to EPSG format for consistent comparison."""
        if crs_str is None:
            return None
        crs_str = str(crs_str).strip().upper()
        if not crs_str.startswith("EPSG:"):
            crs_str = f"EPSG:{crs_str}"
        return crs_str

    if gdf.crs is None:
        if source_crs:
            norm_source = normalize_crs(source_crs)
            print(f"[DEBUG] No CRS in shapefile. Setting to: {norm_source}")
            gdf = gdf.set_crs(norm_source, allow_override=True)
        else:
            gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    else:
        # CRS exists in shapefile
        shapefile_crs_str = gdf.crs.to_string().upper()
        if not shapefile_crs_str.startswith("EPSG:"):
            shapefile_crs_str = f"EPSG:{shapefile_crs_str}"
        
        if source_crs:
            norm_source = normalize_crs(source_crs)
            print(f"[DEBUG] Comparing CRS: shapefile={shapefile_crs_str} vs provided={norm_source}")
            if shapefile_crs_str != norm_source:
                print(f"[DEBUG] CRS mismatch. Reprojecting from {shapefile_crs_str} to {norm_source}")
                gdf = gdf.to_crs(norm_source)
            else:
                print(f"[DEBUG] CRS already matches: {norm_source}")

    print(f"[DEBUG] After CRS handling, GDF CRS: {gdf.crs}")
    print(f"[DEBUG] Sample coordinates after CRS handling: {gdf.geometry.iloc[0] if len(gdf) > 0 else 'No geometries'}")
    
    field_names = [col for col in gdf.columns if col.lower() != "geometry"]
    gdf_wgs84 = gdf.to_crs("EPSG:4326")
    
    print(f"[DEBUG] After conversion to EPSG:4326: {gdf_wgs84.geometry.iloc[0] if len(gdf_wgs84) > 0 else 'No geometries'}")

    for col in gdf_wgs84.columns:
        if gdf_wgs84[col].dtype != "str" and gdf_wgs84[col].dtype != "geometry":
            gdf_wgs84[col] = gdf_wgs84[col].astype(str)
            
    geojson = json.loads(gdf_wgs84.to_json())
    geojson = make_json_serializable(geojson)

    return geojson, field_names


def write_point_geojson_to_shapefile(save_dir, shape_name, geojson, crs="EPSG:4326"):
    """Write point GeoJSON to a shapefile while preserving supported scalar properties."""
    features = geojson.get("features", []) if geojson else []
    clean_features = []
    for feature in features:
        props = feature.get("properties") or {}
        clean_props = {}
        for key, value in props.items():
            if isinstance(value, (str, int, float, bool)) or value is None:
                clean_props[key] = value
            else:
                try:
                    clean_props[key] = json.dumps(value)
                except Exception:
                    clean_props[key] = str(value)
        clean_feature = {
            "type": "Feature",
            "geometry": feature.get("geometry"),
            "properties": clean_props
        }
        clean_features.append(clean_feature)

    gdf = gpd.GeoDataFrame.from_features(
        {"type": "FeatureCollection", "features": clean_features},
        crs=crs
    )
    shp_out = os.path.join(save_dir, shape_name)
    gdf.to_file(shp_out)


def make_json_serializable(value):
    """
    Recursively convert values to strict JSON-safe Python values.

    JSON does not have representations for NaN or +/-Infinity.  If those
    values reach Flask's jsonify(), they can be emitted as the JavaScript
    tokens NaN/Infinity, which causes JSON.parse() in the browser to fail.
    """
    if isinstance(value, dict):
        return {
            key: make_json_serializable(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple)):
        return [make_json_serializable(item) for item in value]

    if isinstance(value, (datetime, date)):
        return value.isoformat()

    if hasattr(value, "to_pydatetime"):
        try:
            return value.to_pydatetime().isoformat()
        except Exception:
            pass

    if hasattr(value, "item"):
        try:
            return make_json_serializable(value.item())
        except Exception:
            pass

    if isinstance(value, float):
        return value if math.isfinite(value) else None

    if isinstance(value, (str, int, bool)) or value is None:
        return value

    return str(value)


def normalize_crs_string(crs_str):
    if crs_str is None:
        return None

    crs_text = str(crs_str).strip()
    if not crs_text.upper().startswith("EPSG:"):
        crs_text = f"EPSG:{crs_text}"
    return crs_text


def create_project_archive():
    if MODEL_STORE["wn"] is None:
        raise ValueError("No model is loaded to export.")

    project_meta = {
        "model_crs": MODEL_STORE["model_crs"],
        "uploaded_layers": {
            "hydrants": {
                "id_field": MODEL_STORE["uploaded_layers"]["hydrants"].get("id_field")
                if MODEL_STORE["uploaded_layers"]["hydrants"] else None
            },
            "valves": {
                "id_field": MODEL_STORE["uploaded_layers"]["valves"].get("id_field")
                if MODEL_STORE["uploaded_layers"]["valves"] else None
            }
        },
        "sequences": [sequence.get("name") for sequence in MODEL_STORE.get("sequences", [])]
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta.json", json.dumps(project_meta))
        archive.writestr("model.pkl", pickle.dumps(MODEL_STORE["wn"], protocol=pickle.HIGHEST_PROTOCOL))

        temp_inp_path = os.path.join(app.config["UPLOAD_FOLDER"], f"project_model_{uuid.uuid4().hex}.inp")
        wntr.network.write_inpfile(MODEL_STORE["wn"], temp_inp_path)
        with open(temp_inp_path, "rb") as inp_file:
            archive.writestr("model.inp", inp_file.read())
        os.remove(temp_inp_path)

        for layer_name in ["hydrants", "valves"]:
            layer = MODEL_STORE["uploaded_layers"].get(layer_name)
            if layer and layer.get("geojson"):
                archive.writestr(f"{layer_name}.geojson", json.dumps(layer["geojson"]))

        for sequence in MODEL_STORE.get("sequences", []):
            sequence_filename = sanitize_sequence_filename(sequence.get("name", "sequence"))
            archive.writestr(f"sequences/{sequence_filename}", sequence_to_text(sequence))

    buffer.seek(0)
    return buffer


def restore_project_archive(project_file):
    with zipfile.ZipFile(project_file, mode="r") as archive:
        if "meta.json" in archive.namelist():
            meta = json.loads(archive.read("meta.json").decode("utf-8"))
        else:
            meta = {}

        wn = None
        model_crs = normalize_crs_string(meta.get("model_crs"))
        inp_path = None

        if "model.pkl" in archive.namelist():
            wn = pickle.loads(archive.read("model.pkl"))

        if "model.inp" in archive.namelist():
            inp_path = os.path.join(app.config["UPLOAD_FOLDER"], f"project_model_{uuid.uuid4().hex}.inp")
            with open(inp_path, "wb") as inp_file:
                inp_file.write(archive.read("model.inp"))
            if wn is None:
                wn = wntr.network.WaterNetworkModel(inp_path)

        if wn is None:
            raise ValueError("Uploaded project archive does not contain a valid model.")

        if inp_path is None:
            inp_path = os.path.join(app.config["UPLOAD_FOLDER"], f"project_model_{uuid.uuid4().hex}.inp")
            wntr.network.write_inpfile(wn, inp_path)

        MODEL_STORE["wn"] = wn
        MODEL_STORE["inp_path"] = inp_path
        MODEL_STORE["model_crs"] = model_crs
        MODEL_STORE["pipe_geojson"] = water_network_pipes_to_geojson(wn=wn, model_crs=model_crs)

        for layer_name in ["hydrants", "valves"]:
            if f"{layer_name}.geojson" in archive.namelist():
                geojson = json.loads(archive.read(f"{layer_name}.geojson").decode("utf-8"))
                field_names = sorted({
                    key
                    for feature in geojson.get("features", [])
                    for key in (feature.get("properties") or {}).keys()
                })
                id_field = (
                    meta.get("uploaded_layers", {}).get(layer_name, {}).get("id_field")
                )
                if id_field not in field_names:
                    id_field = None

                MODEL_STORE["uploaded_layers"][layer_name] = {
                    "path": None,
                    "geojson": geojson,
                    "shape_name": f"{layer_name}.geojson",
                    "fields": field_names,
                    "id_field": id_field
                }
            else:
                MODEL_STORE["uploaded_layers"][layer_name] = None

        sequences = []
        for member_name in archive.namelist():
            if member_name.lower().startswith("sequences/") and member_name.lower().endswith(".txt"):
                text = archive.read(member_name).decode("utf-8")
                sequences.append(parse_sequence_text(text, os.path.basename(member_name)))

        MODEL_STORE["sequences"] = sequences

        return {
            "model_crs": model_crs,
            "pipe_geojson": MODEL_STORE["pipe_geojson"],
            "hydrants": MODEL_STORE["uploaded_layers"]["hydrants"],
            "valves": MODEL_STORE["uploaded_layers"]["valves"],
            "sequences": sequences
        }


def send_project_archive():
    archive_buffer = create_project_archive()
    return send_file(
        archive_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="flushing_journal_project.zip"
    )


def get_uploaded_layer_response(layer_name, layer):
    if not layer:
        return None

    return {
        "geojson": layer["geojson"],
        "fields": layer["fields"],
        "selected_id_field": layer.get("id_field")
    }


def make_project_response():
    return {
        "success": True,
        "model_crs": MODEL_STORE["model_crs"],
        "pipe_geojson": MODEL_STORE["pipe_geojson"],
        "hydrants": get_uploaded_layer_response(MODEL_STORE["uploaded_layers"]["hydrants"]),
        "valves": get_uploaded_layer_response(MODEL_STORE["uploaded_layers"]["valves"]),
        "sequences": MODEL_STORE.get("sequences", [])
    }


def send_json_project_response():
    response = make_project_response()
    return jsonify(response)


def restore_project_request(request_files):
    if "project_zip" not in request_files:
        raise ValueError("No project ZIP file was included in the request.")
    project_file = request_files["project_zip"]
    if project_file.filename == "":
        raise ValueError("No project ZIP file was selected.")
    return restore_project_archive(project_file)


def get_project_download_filename():
    return "flushing_journal_project.zip"


def get_project_upload_filename():
    return "flushing_journal_project.zip"


def maybe_write_project_inp(wn, inp_path):
    if inp_path and os.path.exists(inp_path):
        return inp_path
    new_path = os.path.join(app.config["UPLOAD_FOLDER"], f"project_model_{uuid.uuid4().hex}.inp")
    wntr.network.write_inpfile(wn, new_path)
    return new_path


def get_project_error_response(exc):
    return jsonify({
        "success": False,
        "message": str(exc)
    }), 400


def restore_project_from_file(project_zip):
    return restore_project_archive(project_zip)


def get_project_layer_data(layer_name):
    layer = MODEL_STORE["uploaded_layers"].get(layer_name)
    if not layer:
        return None
    return {
        "geojson": layer["geojson"],
        "fields": layer["fields"],
        "selected_id_field": layer.get("id_field")
    }


def set_project_layers_from_archive(layer_name):
    pass


def get_archive_layer_name(layer_name):
    return f"{layer_name}.geojson"


def water_network_pipes_to_geojson(wn, model_crs):
    """
    Convert WNTR pipe links to Leaflet-friendly GeoJSON in EPSG:4326.

    Assumes WNTR node coordinates are in the CRS provided by model_crs.
    Leaflet expects GeoJSON coordinates as [longitude, latitude].
    """

    if model_crs is None:
        raise ValueError("Model CRS is required to convert model geometries.")

    model_crs_text = str(model_crs).strip()
    if not model_crs_text.upper().startswith("EPSG:"):
        model_crs_text = f"EPSG:{model_crs_text}"

    transformer = Transformer.from_crs(
        model_crs_text,
        "EPSG:4326",
        always_xy=True
    )

    features = []

    for pipe_name in wn.pipe_name_list:
        pipe = wn.get_link(pipe_name)

        start_node = wn.get_node(pipe.start_node_name)
        end_node = wn.get_node(pipe.end_node_name)

        start_coords = getattr(start_node, "coordinates", None)
        end_coords = getattr(end_node, "coordinates", None)

        if not start_coords or not end_coords:
            continue

        coords = [start_coords]
        vertices = getattr(pipe, "vertices", None)
        if vertices:
            coords.extend(vertices)
        coords.append(end_coords)

        transformed_coords = []
        for x, y in coords:
            lon, lat = transformer.transform(x, y)
            transformed_coords.append([lon, lat])

        diameter_meters = safe_float(getattr(pipe, "diameter", None))
        diameter_inches = None
        if diameter_meters is not None:
            diameter_inches = diameter_meters * 39.37007874015748

        feature = {
            "type": "Feature",
            "properties": {
                "id": pipe_name,
                "name": pipe_name,
                "start_node": pipe.start_node_name,
                "end_node": pipe.end_node_name,
                "length": safe_float(getattr(pipe, "length", None)),
                "diameter_meters": diameter_meters,
                "diameter": diameter_inches,
                "roughness": safe_float(getattr(pipe, "roughness", None)),
                "status": str(getattr(pipe, "status", ""))
            },
            "geometry": {
                "type": "LineString",
                "coordinates": transformed_coords
            }
        }

        features.append(feature)

    return make_json_serializable({
        "type": "FeatureCollection",
        "features": features
    })


def safe_float(value):
    """
    Convert numpy/pandas/scalar values to normal JSON-safe floats.
    """

    if value is None:
        return None

    try:
        numeric_value = float(value)
        return numeric_value if math.isfinite(numeric_value) else None
    except Exception:
        return None


if __name__ == "__main__":
    # Spyder-friendly: hard-coded host/port, no argparse
    app.run(host="127.0.0.1", port=5000, debug=True)