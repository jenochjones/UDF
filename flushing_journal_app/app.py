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
from operator import index as index_value
from shapely.geometry import shape, Point, LineString
from shapely.ops import transform as transform_geometry
from shapely.strtree import STRtree

from model import build_steady_state_from_timestep, run_water_network_model

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
    "running_model": None,
    "inp_path": None,
    "model_dir": None,
    "generated_inp_files": [],
    "results_path": None,
    "rpt_path": None,
    "bin_path": None,
    "model_crs": None,
    "model_time": 0,
    "pipe_geojson": None,
    "uploaded_layers": {"valves": None, "hydrants": None, "flushing_zones": None},
    "element_mapping": {"valves": {}, "hydrants": {}},
    "sequences": [],
    "results_dict": {},
    "snapshots": {},
    "connection_options": {
        "lateral_diameter_in": 5.99,
        "lateral_roughness": 1.0,
        "search_distance_ft": 120.0,
    },
    "valve_snap_distance_ft": 120.0,
    "flush_options": {
        "model_timestep": 0,
        "default_orifice_diam": 2.5,
        "volume_turnovers": 3.0,
        "pipes_to_reflush": 1,
        "min_flush_vel": 5.0,
        "start_vel_to_flushing_vel_ratio": 3.0,
    },
}

OPERATION_PROGRESS = {
    "hydrants": {"percent": 0, "message": "Waiting to start…", "done": True},
    "valves": {"percent": 0, "message": "Waiting to start…", "done": True},
    "sequences": {"percent": 0, "message": "Waiting to start…", "done": True},
}


def set_operation_progress(operation, percent, message, done=False, error=False):
    OPERATION_PROGRESS[operation] = {
        "percent": max(0, min(100, int(percent))),
        "message": message,
        "done": done,
        "error": error,
    }


@app.route("/operation_progress/<operation>", methods=["GET"])
def operation_progress(operation):
    if operation not in OPERATION_PROGRESS:
        return jsonify({"success": False, "message": "Unknown operation."}), 404
    return jsonify(OPERATION_PROGRESS[operation])


def set_model_paths(inp_path):
    if not inp_path:
        MODEL_STORE["inp_path"] = None
        MODEL_STORE["rpt_path"] = None
        MODEL_STORE["bin_path"] = None
        return

    MODEL_STORE["inp_path"] = inp_path
    directory = os.path.dirname(inp_path) or os.getcwd()
    file_root = os.path.splitext(os.path.basename(inp_path))[0]
    MODEL_STORE["rpt_path"] = os.path.join(directory, f"{file_root}.rpt")
    MODEL_STORE["bin_path"] = os.path.join(directory, f"{file_root}.bin")


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
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "No inp_file was included in the request.",
                    }
                ),
                400,
            )

        inp_file = request.files["inp_file"]
        model_crs = request.form.get("model_crs", "").strip()
        if model_crs and not model_crs.upper().startswith("EPSG:"):
            model_crs = f"EPSG:{model_crs}"

        if inp_file.filename == "":
            return jsonify({"success": False, "message": "No file was selected."}), 400

        if not model_crs:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Model CRS is required. Example: EPSG:26912",
                    }
                ),
                400,
            )

        filename = secure_filename(inp_file.filename)

        if not filename.lower().endswith(".inp"):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "The selected file must be an EPANET .inp file.",
                    }
                ),
                400,
            )

        project_dir = tempfile.mkdtemp(
            prefix="flushing_journal_project_",
            dir=app.config["UPLOAD_FOLDER"],
        )
        source_inp_path = os.path.join(
            app.config["UPLOAD_FOLDER"], f"upload_{uuid.uuid4().hex}_{filename}"
        )
        inp_file.save(source_inp_path)
        base_model_path = os.path.join(project_dir, "BaseModel.inp")

        model_timestep = 0.0
        try:
            mt_str = request.form.get("model_timestep", "").strip()
            if mt_str:
                model_timestep = float(mt_str)
        except Exception:
            model_timestep = 0.0

        try:
            wn = build_steady_state_from_timestep(
                source_inp_path,
                model_timestep,
                out_inp_path=base_model_path,
            )
        finally:
            if os.path.exists(source_inp_path):
                os.remove(source_inp_path)

        pipe_geojson = water_network_pipes_to_geojson(wn=wn, model_crs=model_crs)

        print(f"[DEBUG] Model CRS: {model_crs}")

        MODEL_STORE["wn"] = wn
        set_model_paths(base_model_path)
        MODEL_STORE["model_dir"] = project_dir
        MODEL_STORE["generated_inp_files"] = []
        MODEL_STORE["results_dict"] = {}
        MODEL_STORE["results_path"] = None
        MODEL_STORE["model_crs"] = model_crs
        MODEL_STORE["model_time"] = model_timestep
        MODEL_STORE["pipe_geojson"] = pipe_geojson
        MODEL_STORE["connection_options"] = {
            "lateral_diameter_in": 5.99,
            "lateral_roughness": 1.0,
            "search_distance_ft": 120.0,
        }
        MODEL_STORE["valve_snap_distance_ft"] = 120.0
        MODEL_STORE["flush_options"] = {
            "model_timestep": model_timestep,
            "default_orifice_diam": 2.5,
            "volume_turnovers": 3.0,
            "pipes_to_reflush": 1,
            "min_flush_vel": 5.0,
            "start_vel_to_flushing_vel_ratio": 3.0,
        }
        response = {
            "success": True,
            "message": "Model loaded successfully.",
            "model_crs": model_crs,
            "model_timestep": model_timestep,
            "snapshot_message": (
                f"Steady-state model created at {model_timestep} h."
            ),
            "pipe_count": len(pipe_geojson.get("features", [])),
            "pipe_geojson": pipe_geojson,
            "options": {
                "connection_options": MODEL_STORE["connection_options"],
                "flush_options": MODEL_STORE["flush_options"],
                "valve_snap_distance_ft": MODEL_STORE["valve_snap_distance_ft"],
            },
        }

        return jsonify(response)

    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/model_pipes", methods=["GET"])
def model_pipes():
    """
    Optional endpoint to retrieve the currently loaded pipe GeoJSON later.
    """

    if MODEL_STORE["pipe_geojson"] is None:
        return (
            jsonify({"success": False, "message": "No model has been loaded yet."}),
            404,
        )

    return jsonify({"success": True, "pipe_geojson": MODEL_STORE["pipe_geojson"]})


@app.route("/download_project", methods=["GET"])
def download_project():
    try:
        return send_project_archive()
    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/upload_project", methods=["POST"])
def upload_project():
    try:
        result = restore_project_request(request.files)

        return jsonify(
            {
                "success": True,
                "message": "Project loaded successfully.",
                "model_crs": result["model_crs"],
                "pipe_geojson": result["pipe_geojson"],
                "hydrants": result["hydrants"],
                "valves": result["valves"],
                "flushing_zones": result.get("flushing_zones"),
                "sequences": result.get("sequences", []),
                "results_dict": result.get("results_dict", {}),
                "options": result.get("options", {}),
            }
        )
    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


def _feature_reference_keys(feature):
    keys = []

    if not isinstance(feature, dict):
        return keys

    properties = feature.get("properties") or {}
    for key in ("id", "ID", "name", "Name"):
        value = properties.get(key)
        if value is not None and str(value).strip() != "":
            keys.append(str(value))

    geometry = feature.get("geometry") or {}
    coordinates = geometry.get("coordinates")
    if isinstance(coordinates, (list, tuple)) and len(coordinates) >= 2:
        try:
            keys.append(f"{float(coordinates[0]):.6f},{float(coordinates[1]):.6f}")
        except (TypeError, ValueError):
            pass

    return keys


def _record_element_mapping(layer_type, feature, model_elements, id_field=None):
    mapping = MODEL_STORE.setdefault("element_mapping", {}).setdefault(layer_type, {})
    properties = feature.get("properties") or {}
    gis_id = properties.get(id_field) if id_field else None
    if gis_id is None or not str(gis_id).strip():
        return

    # Hydrants map to their generated EPANET junction; valves map to the
    # EPANET link their GIS point was snapped to.
    element_name = (
        model_elements.get("node") if layer_type == "hydrants"
        else model_elements.get("pipe")
    )
    if element_name is not None and str(element_name).strip():
        mapping[str(gis_id).strip()] = str(element_name).strip()
    feature.setdefault("properties", {})["model_elements"] = model_elements


def _restore_element_mapping_from_layers():
    MODEL_STORE["element_mapping"] = {"valves": {}, "hydrants": {}}
    for layer_type in ("hydrants", "valves"):
        layer = MODEL_STORE["uploaded_layers"].get(layer_type)
        if not layer or not layer.get("geojson"):
            continue
        for feature in layer["geojson"].get("features", []):
            model_elements = (feature.get("properties") or {}).get("model_elements")
            if not model_elements:
                properties = feature.get("properties") or {}
                if layer_type == "hydrants" and properties.get("hydrant_pipe_name"):
                    model_elements = {
                        "node": properties.get("hydrant_junction_name"),
                        "pipe": properties.get("hydrant_pipe_name"),
                        "connection_node": properties.get("connection_node_name"),
                    }
                elif layer_type == "valves" and properties.get("model_pipe_name"):
                    model_elements = {
                        "pipe": properties.get("model_pipe_name"),
                        "nodes": properties.get("model_pipe_nodes", []),
                    }
            if model_elements:
                _record_element_mapping(
                    layer_type, feature, model_elements, layer.get("id_field")
                )


def _refresh_mapping_aliases(layer_type):
    layer = MODEL_STORE["uploaded_layers"].get(layer_type)
    if not layer or not layer.get("geojson"):
        return
    MODEL_STORE.setdefault("element_mapping", {})[layer_type] = {}
    for feature in layer["geojson"].get("features", []):
        model_elements = (feature.get("properties") or {}).get("model_elements")
        if model_elements:
            _record_element_mapping(
                layer_type, feature, model_elements, layer.get("id_field")
            )


def _filter_modified_features(layer_type, modified_features):
    layer = MODEL_STORE["uploaded_layers"].get(layer_type)
    if not layer or not layer.get("geojson"):
        return []

    features = layer["geojson"].get("features", [])
    if not modified_features:
        return features

    target_keys = set()
    for feature in modified_features:
        target_keys.update(_feature_reference_keys(feature))

    if not target_keys:
        return features

    filtered = []
    for feature in features:
        feature_keys = _feature_reference_keys(feature)
        if any(key in target_keys for key in feature_keys):
            filtered.append(feature)
    return filtered


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
                geometries.append(
                    {"name": current_pipe_name, "geometry": LineString(coords)}
                )

        return geometries

    # Connect each uploaded hydrant to the nearest pipe in the loaded WNTR model.
    set_operation_progress("hydrants", 1, "Preparing hydrant connection…")
    try:
        data = request.get_json(silent=True) or {}
        modified_hydrants = data.get("hydrants") or []
        requested_options = data.get("connection_options")
        connection_options = dict(MODEL_STORE.get("connection_options", {}))
        if requested_options is not None:
            if not isinstance(requested_options, dict):
                raise ValueError("Hydrant connection options must be an object.")
            connection_options.update(requested_options)

        try:
            lateral_diameter_in = float(connection_options["lateral_diameter_in"])
            lateral_roughness = float(connection_options["lateral_roughness"])
            search_distance_ft = float(connection_options["search_distance_ft"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("Hydrant connection values must be numeric.") from exc
        if not all(
            math.isfinite(value)
            for value in (lateral_diameter_in, lateral_roughness, search_distance_ft)
        ):
            raise ValueError("Hydrant connection values must be finite numbers.")
        if lateral_diameter_in <= 0 or lateral_roughness <= 0 or search_distance_ft < 0:
            raise ValueError(
                "Lateral diameter and roughness must be greater than zero; "
                "search distance cannot be negative."
            )

        connection_options = {
            "lateral_diameter_in": lateral_diameter_in,
            "lateral_roughness": lateral_roughness,
            "search_distance_ft": search_distance_ft,
        }

        if MODEL_STORE["wn"] is None:
            return (
                jsonify({"success": False, "message": "No model has been loaded yet."}),
                400,
            )

        hydrants_layer = MODEL_STORE["uploaded_layers"].get("hydrants")
        if not hydrants_layer or not hydrants_layer["geojson"].get("features"):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "No hydrants shapefile has been uploaded.",
                    }
                ),
                400,
            )

        if MODEL_STORE["pipe_geojson"] is None:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "No model pipe geometry is available.",
                    }
                ),
                400,
            )

        wn = MODEL_STORE["wn"]
        model_crs = MODEL_STORE["model_crs"]

        if modified_hydrants:
            hydrant_features = _filter_modified_features("hydrants", modified_hydrants)
        else:
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
        model_crs_info = CRS.from_user_input(model_crs)
        if not model_crs_info.is_projected or not model_crs_info.axis_info:
            raise ValueError(
                "Hydrant search distance requires a projected model coordinate system."
            )
        model_units_to_meters = model_crs_info.axis_info[0].unit_conversion_factor
        if not model_units_to_meters or not math.isfinite(model_units_to_meters):
            raise ValueError("Could not determine model coordinate units.")
        search_distance_model_units = (
            search_distance_ft * 0.3048 / model_units_to_meters
        )
        set_operation_progress("hydrants", 4, "Building model pipe geometries…")
        pipe_geometries = build_pipe_geometries(wn)

        if not pipe_geometries:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "The loaded model contains no pipe geometries.",
                    }
                ),
                400,
            )

        transformer_to_model = Transformer.from_crs(
            "EPSG:4326", model_crs, always_xy=True
        )

        set_operation_progress("hydrants", 8, "Preparing nearest-pipe search…")

        hydrant_id_field = hydrants_layer.get("id_field")
        connected_count = 0
        skipped_count = 0
        node_names = set(wn.node_name_list)
        link_names = set(wn.link_name_list)
        pipe_tree = STRtree([item["geometry"] for item in pipe_geometries])

        def nearest_pipe_for(point):
            """Return the indexed pipe nearest to a point (Shapely 1.x/2.x)."""
            result = pipe_tree.nearest(point)
            try:
                return pipe_geometries[index_value(result)]
            except TypeError:
                pass
            # Shapely 1.x returns the geometry itself; identity mapping avoids
            # repeatedly comparing every geometry in Python.
            return pipe_by_geometry_id[id(result)]

        pipe_by_geometry_id = {
            id(item["geometry"]): item for item in pipe_geometries
        }

        total_hydrants = len(hydrant_features)
        for hydrant_index, hydrant_feature in enumerate(hydrant_features):
            completed_fraction = hydrant_index / max(1, total_hydrants)
            progress_percent = 8 + int(completed_fraction * 74)
            set_operation_progress(
                "hydrants",
                progress_percent,
                f"Connecting hydrant {hydrant_index + 1} of {total_hydrants}…",
            )
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
                hydrant_point_4326.x, hydrant_point_4326.y
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

            previous_pipe_name = hydrant_feature.get("properties", {}).get("hydrant_pipe_name")
            previous_junction_name = hydrant_feature.get("properties", {}).get("hydrant_junction_name")

            if previous_pipe_name and previous_pipe_name in link_names:
                try:
                    wn.remove_link(previous_pipe_name)
                    link_names.discard(previous_pipe_name)
                except Exception:
                    pass

            if previous_junction_name and previous_junction_name in node_names:
                try:
                    if not wn.get_links_for_node(previous_junction_name):
                        wn.remove_node(previous_junction_name)
                        node_names.discard(previous_junction_name)
                except Exception:
                    pass

            hydrant_junction_name = make_unique_node_name(hydrant_junction_name, wn)

            nearest_pipe = nearest_pipe_for(hydrant_point)
            if (
                nearest_pipe["geometry"].distance(hydrant_point)
                > search_distance_model_units
            ):
                skipped_count += 1
                if hydrant_id_field and properties.get(hydrant_id_field) is not None:
                    MODEL_STORE["element_mapping"].setdefault("hydrants", {}).pop(
                        str(properties[hydrant_id_field]).strip(), None
                    )
                for property_name in (
                    "model_elements",
                    "hydrant_junction_name",
                    "connection_node_name",
                    "hydrant_pipe_name",
                ):
                    properties.pop(property_name, None)
                continue

            pipe_name = nearest_pipe["name"]
            pipe_line = nearest_pipe["geometry"]
            pipe = wn.get_link(pipe_name)

            if pipe is None:
                skipped_count += 1
                continue

            hydrant_pipe_diameter_m = min(
                lateral_diameter_in * 0.0254,
                float(pipe.diameter),
            )
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
                    split_at_point=split_fraction,
                )

                pipe_base_names[pipe_name] = base_pipe_name
                pipe_base_names[new_pipe_name] = base_pipe_name
                node_names.add(connection_node_name)
                link_names.add(new_pipe_name)

                connection_node = wn.get_node(connection_node_name)
                connection_node.coordinates = (x_split, y_split)

                start_elev = start_node.elevation
                end_elev = end_node.elevation
                connection_elevation = start_elev + split_fraction * (
                    end_elev - start_elev
                )
                connection_node.elevation = connection_elevation

                set_operation_progress(
                    "hydrants",
                    progress_percent,
                    f"Updating pipe network after hydrant {hydrant_index + 1}…",
                )
                pipe_geometries = build_pipe_geometries(wn)
                pipe_tree = STRtree([item["geometry"] for item in pipe_geometries])
                pipe_by_geometry_id = {
                    id(item["geometry"]): item for item in pipe_geometries
                }
                for refreshed_pipe_name, _ in wn.pipes():
                    if refreshed_pipe_name not in pipe_base_names:
                        pipe_base_names[refreshed_pipe_name] = refreshed_pipe_name

            if hydrant_junction_name not in node_names:
                wn.add_junction(
                    hydrant_junction_name,
                    base_demand=0.0,
                    elevation=connection_elevation,
                    coordinates=(x_hyd, y_hyd),
                )
                node_names.add(hydrant_junction_name)

            hydrant_pipe_base_name = f"{hydrant_junction_name}_pipe"
            hydrant_pipe_name = make_unique_link_name(
                f"{hydrant_pipe_base_name}_{uuid.uuid4().hex[:6]}", wn
            )

            hydrant_pipe_length = float(split_pt.distance(Point(x_hyd, y_hyd)))
            if hydrant_pipe_length <= 0:
                hydrant_pipe_length = 0.01

            headloss_formula = wn.options.hydraulic.headloss
            
            if headloss_formula == "D-W":
                lateral_roughness_conv = lateral_roughness * 0.001 * 0.3048
            else:
                lateral_roughness_conv = lateral_roughness

            wn.add_pipe(
                hydrant_pipe_name,
                hydrant_junction_name,
                connection_node_name,
                length=hydrant_pipe_length,
                diameter=hydrant_pipe_diameter_m,
                roughness=lateral_roughness_conv,
                minor_loss=0.0,
                initial_status="OPEN",
            )
            link_names.add(hydrant_pipe_name)

            hydrant_feature.setdefault("properties", {})
            hydrant_feature["properties"]["hydrant_junction_name"] = hydrant_junction_name
            hydrant_feature["properties"]["connection_node_name"] = connection_node_name
            hydrant_feature["properties"]["hydrant_pipe_name"] = hydrant_pipe_name
            _record_element_mapping(
                "hydrants",
                hydrant_feature,
                {
                    "node": hydrant_junction_name,
                    "pipe": hydrant_pipe_name,
                    "network_pipe": pipe_name,
                    "connection_node": connection_node_name,
                },
                hydrant_id_field,
            )

            connected_count += 1

        set_operation_progress("hydrants", 84, "Updating model pipe map…")
        MODEL_STORE["pipe_geojson"] = water_network_pipes_to_geojson(
            wn=wn, model_crs=model_crs
        )
        MODEL_STORE["uploaded_layers"]["hydrants"]["geojson"]["features"] = hydrants_layer["geojson"]["features"]

        MODEL_STORE["wn"] = wn
        MODEL_STORE["connection_options"] = connection_options

        if MODEL_STORE["inp_path"]:
            set_operation_progress("hydrants", 94, "Saving updated water network…")
            wntr.network.write_inpfile(wn, MODEL_STORE["inp_path"])

        set_operation_progress("hydrants", 100, "Hydrants connected successfully.", done=True)

        return jsonify(
            {
                "success": True,
                "message": (
                    f"Connected {connected_count} hydrant(s); skipped "
                    f"{skipped_count} hydrant(s), including those outside the "
                    f"{search_distance_ft:g} ft search distance."
                ),
                "connected_count": connected_count,
                "skipped_count": skipped_count,
                "connection_options": connection_options,
                "search_distance_ft": search_distance_ft,
                "pipe_geojson": MODEL_STORE["pipe_geojson"],
            }
        )
    except ValueError as exc:
        set_operation_progress("hydrants", 100, str(exc), done=True, error=True)
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        set_operation_progress("hydrants", 100, str(exc), done=True, error=True)
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/snap_valves", methods=["POST"])
def snap_valves():
    set_operation_progress("valves", 1, "Preparing valve snapping…")
    try:
        data = request.get_json(silent=True) or {}
        modified_valves = data.get("valves") or []
        snap_distance_value = data.get(
            "snap_distance_ft", MODEL_STORE.get("valve_snap_distance_ft", 120.0)
        )
        try:
            snap_distance_ft = float(snap_distance_value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Valve snap distance must be numeric.") from exc
        if not math.isfinite(snap_distance_ft) or snap_distance_ft < 0:
            raise ValueError("Valve snap distance must be a finite, non-negative number.")

        model_crs = MODEL_STORE.get("model_crs")
        if not model_crs:
            raise ValueError("Model coordinate system is required to snap valves.")
        model_crs_info = CRS.from_user_input(model_crs)
        if not model_crs_info.is_projected or not model_crs_info.axis_info:
            raise ValueError(
                "Valve snap distance requires a projected model coordinate system."
            )
        model_units_to_meters = model_crs_info.axis_info[0].unit_conversion_factor
        if not model_units_to_meters or not math.isfinite(model_units_to_meters):
            raise ValueError("Could not determine model coordinate units.")
        snap_distance_model_units = (
            snap_distance_ft * 0.3048 / model_units_to_meters
        )
        to_model_crs = Transformer.from_crs(
            "EPSG:4326", model_crs_info, always_xy=True
        )
        to_geojson_crs = Transformer.from_crs(
            model_crs_info, "EPSG:4326", always_xy=True
        )

        if MODEL_STORE["pipe_geojson"] is None:
            return (
                jsonify({"success": False, "message": "No model has been loaded yet."}),
                400,
            )

        valves_layer = MODEL_STORE["uploaded_layers"].get("valves")
        if (
            not valves_layer
            or not valves_layer.get("geojson")
            or not valves_layer["geojson"].get("features")
        ):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "No valves shapefile has been uploaded.",
                    }
                ),
                400,
            )

        pipe_features = MODEL_STORE["pipe_geojson"].get("features", [])
        total_pipes = len(pipe_features)
        pipe_geometries = []
        valid_pipe_features = []
        pipe_feature_by_geometry_id = {}
        for pipe_index, pipe_feature in enumerate(pipe_features):
            if pipe_index % max(1, total_pipes // 20 or 1) == 0:
                set_operation_progress(
                    "valves",
                    2 + int((pipe_index / max(1, total_pipes)) * 7),
                    f"Preparing pipe geometry {pipe_index + 1} of {total_pipes}…",
                )
            geometry = pipe_feature.get("geometry")
            if not geometry:
                continue
            try:
                pipe_geometry = transform_geometry(
                    to_model_crs.transform, shape(geometry)
                )
            except Exception:
                continue
            if pipe_geometry.is_valid:
                pipe_geometries.append(pipe_geometry)
                valid_pipe_features.append(pipe_feature)
                pipe_feature_by_geometry_id[id(pipe_geometry)] = pipe_feature

        if not pipe_geometries:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "The loaded model does not contain any pipe geometries.",
                    }
                ),
                400,
            )

        all_features = valves_layer["geojson"].get("features", [])
        features = all_features
        if modified_valves:
            features = _filter_modified_features("valves", modified_valves)

        set_operation_progress("valves", 10, "Preparing nearest-pipe search…")
        pipe_tree = STRtree(pipe_geometries)

        total_valves = len(features)
        connected_count = 0
        skipped_count = 0
        for valve_index, feature in enumerate(features):
            completed_fraction = valve_index / max(1, total_valves)
            set_operation_progress(
                "valves",
                10 + int(completed_fraction * 76),
                f"Snapping valve {valve_index + 1} of {total_valves}…",
            )
            geometry = feature.get("geometry")
            if not geometry:
                skipped_count += 1
                continue

            point = transform_geometry(to_model_crs.transform, shape(geometry))
            nearest_pipe = pipe_tree.nearest(point)
            try:
                nearest_pipe_index = index_value(nearest_pipe)
                nearest_pipe_feature = valid_pipe_features[nearest_pipe_index]
                nearest_pipe = pipe_geometries[nearest_pipe_index]
            except TypeError:
                nearest_pipe_feature = pipe_feature_by_geometry_id[id(nearest_pipe)]
            if nearest_pipe.distance(point) > snap_distance_model_units:
                skipped_count += 1
                properties = feature.setdefault("properties", {})
                id_field = valves_layer.get("id_field")
                valve_id = properties.get(id_field) if id_field else None
                if valve_id is not None:
                    MODEL_STORE["element_mapping"].setdefault("valves", {}).pop(
                        str(valve_id).strip(), None
                    )
                for property_name in (
                    "model_elements",
                    "model_pipe_name",
                    "model_pipe_nodes",
                ):
                    properties.pop(property_name, None)
                continue

            best_location = nearest_pipe.interpolate(nearest_pipe.project(point))

            if best_location is not None:
                longitude, latitude = to_geojson_crs.transform(
                    best_location.x, best_location.y
                )
                feature["geometry"]["coordinates"] = [longitude, latitude]
            pipe_properties = nearest_pipe_feature.get("properties") or {}
            pipe_name = pipe_properties.get("id") or pipe_properties.get("name")
            feature.setdefault("properties", {})["model_pipe_name"] = pipe_name
            feature["properties"]["model_pipe_nodes"] = [
                node
                for node in (
                    pipe_properties.get("start_node"),
                    pipe_properties.get("end_node"),
                )
                if node is not None
            ]
            _record_element_mapping(
                "valves",
                feature,
                {
                    "pipe": pipe_name,
                    "nodes": feature["properties"]["model_pipe_nodes"],
                },
                valves_layer.get("id_field"),
            )
            connected_count += 1

        MODEL_STORE["valve_snap_distance_ft"] = snap_distance_ft

        set_operation_progress("valves", 88, "Saving snapped valve locations…")

        save_dir = MODEL_STORE["uploaded_layers"]["valves"].get("path")
        shape_name = MODEL_STORE["uploaded_layers"]["valves"].get("shape_name")
        if save_dir and shape_name:
            try:
                write_point_geojson_to_shapefile(
                    save_dir,
                    shape_name,
                    {"type": "FeatureCollection", "features": all_features},
                    crs="EPSG:4326",
                )
            except Exception as e:
                print(
                    "Warning: failed to write snapped valves shapefile back to disk:", e
                )

        set_operation_progress(
            "valves",
            100,
            f"Snapped {connected_count} valve(s); skipped {skipped_count} outside "
            f"the {snap_distance_ft:g} ft snap distance.",
            done=True,
        )
        return jsonify(
            {
                "success": True,
                "message": (
                    f"Snapped {connected_count} valve(s); skipped {skipped_count} "
                    f"outside the {snap_distance_ft:g} ft snap distance."
                ),
                "connected_count": connected_count,
                "skipped_count": skipped_count,
                "snap_distance_ft": snap_distance_ft,
                "geojson": {
                    "type": "FeatureCollection",
                    "features": all_features,
                },
            }
        )
    except ValueError as exc:
        set_operation_progress("valves", 100, str(exc), done=True, error=True)
        return jsonify({"success": False, "message": str(exc)}), 400
    except Exception as exc:
        set_operation_progress("valves", 100, str(exc), done=True, error=True)
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/set_layer_id_field", methods=["POST"])
def set_layer_id_field():
    try:
        data = request.get_json(silent=True) or {}
        layer_type = data.get("layer_type", "").strip().lower()
        id_field = data.get("id_field", "").strip()

        if layer_type not in {"valves", "hydrants"}:
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Layer type must be valves or hydrants.",
                    }
                ),
                400,
            )

        layer = MODEL_STORE["uploaded_layers"].get(layer_type)
        if not layer or not layer.get("geojson"):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "No layer has been uploaded for that type.",
                    }
                ),
                400,
            )

        if not id_field:
            return (
                jsonify({"success": False, "message": "An ID field must be provided."}),
                400,
            )

        if id_field not in layer.get("fields", []):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Selected ID field is not available in the uploaded layer.",
                    }
                ),
                400,
            )

        layer["id_field"] = id_field
        _refresh_mapping_aliases(layer_type)

        return jsonify(
            {
                "success": True,
                "message": "Layer ID field saved.",
                "layer_type": layer_type,
                "selected_id_field": id_field,
            }
        )

    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


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
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Layer type must be hydrants or valves.",
                    }
                ),
                400,
            )

        if not feature or not isinstance(feature, dict) or not feature.get("geometry"):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "A feature with geometry must be provided.",
                    }
                ),
                400,
            )

        layer = MODEL_STORE["uploaded_layers"].get(layer_type)
        if not layer or not layer.get("geojson"):
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "No uploaded layer found for that type.",
                    }
                ),
                400,
            )

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
                    if (
                        key in props
                        and feature.get("properties")
                        and props.get(key) == feature.get("properties").get(key)
                    ):
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
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Could not locate matching feature to update.",
                    }
                ),
                404,
            )

        # Preserve the stable GIS-to-model identity while replacing edited data.
        existing_properties = features[matched_index].get("properties") or {}
        updated_properties = feature.get("properties") or {}
        if existing_properties.get("_mapping_id"):
            updated_properties.setdefault("_mapping_id", existing_properties["_mapping_id"])
        if existing_properties.get("model_elements"):
            updated_properties.setdefault("model_elements", existing_properties["model_elements"])

        # Replace geometry (and optionally properties) for the matched feature
        features[matched_index]["geometry"] = feature.get("geometry")
        # Optionally update properties if provided
        if feature.get("properties"):
            features[matched_index]["properties"] = updated_properties

        # Write back into model store
        MODEL_STORE["uploaded_layers"][layer_type]["geojson"]["features"] = features

        # If shapefile exists on disk, attempt to overwrite it with updated geojson
        save_dir = MODEL_STORE["uploaded_layers"][layer_type].get("path")
        shape_name = MODEL_STORE["uploaded_layers"][layer_type].get("shape_name")
        if save_dir and shape_name:
            try:
                write_point_geojson_to_shapefile(
                    save_dir,
                    shape_name,
                    {"type": "FeatureCollection", "features": features},
                    crs="EPSG:4326",
                )
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
            return (
                jsonify(
                    {
                        "success": False,
                        "message": "Layer type must be either valves or hydrants.",
                    }
                ),
                400,
            )

        uploaded_files = request.files.getlist("shape_files")
        if not uploaded_files or all(file.filename == "" for file in uploaded_files):
            return (
                jsonify(
                    {"success": False, "message": "No shapefile files were provided."}
                ),
                400,
            )

        shp_file = None
        save_dir = os.path.join(
            app.config["UPLOAD_FOLDER"], f"{layer_type}_{uuid.uuid4().hex[:8]}"
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
            return (
                jsonify(
                    {"success": False, "message": "A .shp file is required for upload."}
                ),
                400,
            )

        source_crs_value = request.form.get("source_crs", "").strip()
        selected_id_field = request.form.get("id_field", "").strip() or None
        shp_path = os.path.join(save_dir, shp_file)

        geojson, field_names = point_shapefile_to_geojson(
            shp_path=shp_path, source_crs=source_crs_value or None
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

        MODEL_STORE.setdefault("element_mapping", {})[layer_type] = {}

        MODEL_STORE["uploaded_layers"][layer_type] = {
            "path": save_dir,
            "geojson": geojson,
            "shape_name": shp_file,
            "fields": field_names,
            "id_field": selected_id_field,
        }
        print("Done")

        return jsonify(
            {
                "success": True,
                "message": f"{layer_type.title()} shapefile loaded successfully.",
                "layer_type": layer_type,
                "feature_count": len(geojson.get("features", [])),
                "geojson": geojson,
                "field_names": field_names,
                "selected_id_field": selected_id_field,
            }
        )

    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/upload_flushing_zones", methods=["POST"])
def upload_flushing_zones():
    try:
        uploaded_files = request.files.getlist("shape_files")
        if not uploaded_files or all(file.filename == "" for file in uploaded_files):
            return jsonify({"success": False, "message": "Select the shapefile components to upload."}), 400
        save_dir = os.path.join(app.config["UPLOAD_FOLDER"], f"flushing_zones_{uuid.uuid4().hex[:8]}")
        os.makedirs(save_dir, exist_ok=True)
        shp_file = None
        for uploaded_file in uploaded_files:
            if uploaded_file.filename:
                filename = secure_filename(uploaded_file.filename)
                uploaded_file.save(os.path.join(save_dir, filename))
                if filename.lower().endswith(".shp"):
                    shp_file = filename
        if not shp_file:
            return jsonify({"success": False, "message": "A .shp file is required."}), 400
        gdf = gpd.read_file(os.path.join(save_dir, shp_file))
        if gdf.empty or not set(gdf.geom_type.str.lower().unique()).issubset({"polygon", "multipolygon"}):
            return jsonify({"success": False, "message": "Flushing zones must contain polygon features."}), 400
        if gdf.crs is None:
            source_crs = request.form.get("source_crs", "").strip()
            if not source_crs:
                raise ValueError("The shapefile has no CRS; define its projection before uploading.")
            gdf = gdf.set_crs(source_crs)
        gdf = gdf.to_crs("EPSG:4326")
        fields = [str(column) for column in gdf.columns if column != gdf.geometry.name]
        geojson = json.loads(gdf.to_json(drop_id=True))
        MODEL_STORE["uploaded_layers"]["flushing_zones"] = {"path": save_dir, "geojson": make_json_serializable(geojson), "shape_name": shp_file, "fields": fields, "label_field": None}
        return jsonify({"success": True, "geojson": geojson, "field_names": fields, "feature_count": len(gdf)})
    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/set_flushing_zone_label_field", methods=["POST"])
def set_flushing_zone_label_field():
    layer = MODEL_STORE["uploaded_layers"].get("flushing_zones")
    field = (request.get_json(silent=True) or {}).get("field")
    if not layer or (field and field not in layer.get("fields", [])):
        return jsonify({"success": False, "message": "Invalid flushing zone field."}), 400
    layer["label_field"] = field or None
    visible = (request.get_json(silent=True) or {}).get("labels_visible")
    if isinstance(visible, bool):
        layer["labels_visible"] = visible
    return jsonify({"success": True, "field": layer["label_field"]})


@app.route("/upload_sequences", methods=["POST"])
def upload_sequences():
    """
    Upload one or more sequence text files, parse them on the backend,
    store the sequence array, and return it to the frontend.
    """
    try:
        uploaded_files = request.files.getlist("sequence_files")
        if not uploaded_files or all(file.filename == "" for file in uploaded_files):
            return (
                jsonify(
                    {"success": False, "message": "No sequence files were provided."}
                ),
                400,
            )

        sequences = []
        for uploaded_file in uploaded_files:
            if uploaded_file.filename == "":
                continue

            filename = secure_filename(uploaded_file.filename)
            if not filename.lower().endswith(".txt"):
                return (
                    jsonify(
                        {
                            "success": False,
                            "message": "Only .txt sequence files are supported.",
                        }
                    ),
                    400,
                )

            text = uploaded_file.stream.read().decode("utf-8", errors="replace")
            sequence = parse_sequence_text(text, filename)
            sequences.append(sequence)

        MODEL_STORE["sequences"] = sequences

        return jsonify(
            {
                "success": True,
                "message": f"Loaded {len(sequences)} sequence file(s).",
                "sequences": sequences,
            }
        )
    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/save_sequences", methods=["POST"])
def save_sequences():
    try:
        data = request.get_json(silent=True) or {}
        sequences = data.get("sequences")

        if sequences is None:
            return (
                jsonify({"success": False, "message": "No sequences were provided."}),
                400,
            )

        if not isinstance(sequences, list):
            return (
                jsonify({"success": False, "message": "Sequences must be an array."}),
                400,
            )

        MODEL_STORE["sequences"] = sequences

        return jsonify({"success": True, "message": "Sequences saved."})
    except Exception as exc:
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


def receive_sequence_run_request(expected_count=None):
    data = request.get_json(silent=True) or {}
    sequences = data.get("sequences")
    options = data.get("options")

    if options is not None and not isinstance(options, dict):
        return None, None, (
            jsonify({"success": False, "message": "Flushing options must be an object."}),
            400,
        )

    if not isinstance(sequences, list):
        return None, None, (
            jsonify({"success": False, "message": "Sequences must be an array."}),
            400,
        )

    if not sequences:
        return None, None, (
            jsonify(
                {"success": False, "message": "At least one sequence is required."}
            ),
            400,
        )

    if expected_count is not None and len(sequences) != expected_count:
        return None, None, (
            jsonify(
                {
                    "success": False,
                    "message": f"Exactly {expected_count} sequence is required.",
                }
            ),
            400,
        )

    for sequence in sequences:
        if not isinstance(sequence, dict) or not isinstance(
            sequence.get("operations"), list
        ):
            return None, None, (
                jsonify(
                    {
                        "success": False,
                        "message": "Each sequence must include an operations array.",
                    }
                ),
                400,
            )

    return sequences, options, None


def save_project_results(results_dict):
    model_dir = MODEL_STORE.get("model_dir") or os.path.dirname(
        MODEL_STORE.get("inp_path") or ""
    )
    if not model_dir:
        raise ValueError("No project directory is available to save simulation results.")

    os.makedirs(model_dir, exist_ok=True)
    results_path = os.path.join(model_dir, "results.txt")
    with open(results_path, "w", encoding="utf-8") as results_file:
        json.dump(results_dict, results_file, indent=2, allow_nan=False)

    MODEL_STORE["results_dict"] = results_dict
    MODEL_STORE["results_path"] = results_path


@app.route("/run_sequences", methods=["POST"])
def run_sequences():
    sequences, options, error = receive_sequence_run_request()
    if error:
        return error
    if sequences is None:
        return jsonify({"success": False, "message": "Sequences are required."}), 400

    try:
        set_operation_progress("sequences", 1, "Preparing sequences...")
        results_dict = run_water_network_model(
            MODEL_STORE,
            sequences,
            options,
            progress_callback=lambda percent, message: set_operation_progress(
                "sequences", percent, message
            ),
        )
        MODEL_STORE["sequences"] = sequences
        save_project_results(results_dict)
        set_operation_progress(
            "sequences", 100, "Sequence run completed.", done=True
        )
        return jsonify(
            {
                "success": True,
                "message": f"Received {len(sequences)} sequence(s) for processing.",
                "sequences": sequences,
                "results_dict": results_dict,
                "options": {
                    "connection_options": MODEL_STORE.get("connection_options", {}),
                    "flush_options": MODEL_STORE.get("flush_options", {}),
                    "valve_snap_distance_ft": MODEL_STORE.get(
                        "valve_snap_distance_ft", 120.0
                    ),
                },
            }
        )
    except Exception as exc:
        set_operation_progress(
            "sequences", 100, str(exc), done=True, error=True
        )
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


@app.route("/run_sequence", methods=["POST"])
def run_sequence():
    sequences, options, error = receive_sequence_run_request(expected_count=1)
    if error:
        return error
    if sequences is None:
        return jsonify({"success": False, "message": "A sequence is required."}), 400

    try:
        set_operation_progress("sequences", 1, "Preparing sequence...")
        results_dict = run_water_network_model(
            MODEL_STORE,
            sequences,
            options,
            progress_callback=lambda percent, message: set_operation_progress(
                "sequences", percent, message
            ),
        )
        stored_sequences = MODEL_STORE.get("sequences", [])
        updated_sequences = list(stored_sequences)
        for sequence in sequences:
            sequence_index = next(
                (
                    index
                    for index, stored_sequence in enumerate(updated_sequences)
                    if stored_sequence.get("name") == sequence.get("name")
                ),
                None,
            )
            if sequence_index is None:
                updated_sequences.append(sequence)
            else:
                updated_sequences[sequence_index] = sequence
        MODEL_STORE["sequences"] = updated_sequences

        stored_results = dict(MODEL_STORE.get("results_dict", {}))
        for sequence_name, sequence_results in results_dict.items():
            merged_sequence_results = dict(stored_results.get(sequence_name, {}))
            merged_sequence_results.update(sequence_results)
            stored_results[sequence_name] = merged_sequence_results
        save_project_results(stored_results)
        set_operation_progress(
            "sequences", 100, "Sequence run completed.", done=True
        )
        return jsonify(
            {
                "success": True,
                "message": "Received the current sequence for processing.",
                "sequences": updated_sequences,
                "results_dict": stored_results,
                "options": {
                    "connection_options": MODEL_STORE.get("connection_options", {}),
                    "flush_options": MODEL_STORE.get("flush_options", {}),
                    "valve_snap_distance_ft": MODEL_STORE.get(
                        "valve_snap_distance_ft", 120.0
                    ),
                },
            }
        )
    except Exception as exc:
        set_operation_progress(
            "sequences", 100, str(exc), done=True, error=True
        )
        print(traceback.format_exc())
        return jsonify({"success": False, "message": str(exc)}), 500


def parse_sequence_text(text, filename=None):
    sequence = {
        "name": (
            filename[:-4]
            if filename and filename.lower().endswith(".txt")
            else (filename or "Sequence")
        ),
        "operations": [],
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
            open_valves = [
                val.strip()
                for val in open_valves_match.group(1).split(",")
                if val.strip()
            ]

        close_valves_match = re.search(r"<([^<>]*)>", block)
        if close_valves_match:
            close_valves = [
                val.strip()
                for val in close_valves_match.group(1).split(",")
                if val.strip()
            ]

        hydrants_match = re.search(r"\{([^}]*)\}", block)
        if hydrants_match:
            hydrants_value = hydrants_match.group(1).strip()
            if hydrants_value:
                for token in hydrants_value.split(","):
                    parts = token.split("*", 1)
                    hydrant_id = parts[0].strip()
                    if hydrant_id:
                        open_hydrants.append(hydrant_id)
                    if len(parts) > 1 and parts[1].strip() and not orifice_size:
                        orifice_size = parts[1].strip()

        map_message_match = re.search(r"\|([^|]*)\|", block)
        if map_message_match:
            map_message = map_message_match.group(1).strip()

        sequence["operations"].append(
            {
                "name": operation_name,
                "open_valves": open_valves,
                "close_valves": close_valves,
                "open_hydrants": open_hydrants,
                "orifice_size": orifice_size,
                "target_velocity": target_velocity,
                "toggle_mode": "Orifice Size",
                "map_message": map_message,
            }
        )

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
    print(
        f"[DEBUG] Sample coordinates before transformation: {gdf.geometry.iloc[0] if len(gdf) > 0 else 'No geometries'}"
    )

    if gdf.empty:
        return {"type": "FeatureCollection", "features": []}, []

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
            print(
                f"[DEBUG] Comparing CRS: shapefile={shapefile_crs_str} vs provided={norm_source}"
            )
            if shapefile_crs_str != norm_source:
                print(
                    f"[DEBUG] CRS mismatch. Reprojecting from {shapefile_crs_str} to {norm_source}"
                )
                gdf = gdf.to_crs(norm_source)
            else:
                print(f"[DEBUG] CRS already matches: {norm_source}")

    print(f"[DEBUG] After CRS handling, GDF CRS: {gdf.crs}")
    print(
        f"[DEBUG] Sample coordinates after CRS handling: {gdf.geometry.iloc[0] if len(gdf) > 0 else 'No geometries'}"
    )

    field_names = [col for col in gdf.columns if col.lower() != "geometry"]
    gdf_wgs84 = gdf.to_crs("EPSG:4326")

    print(
        f"[DEBUG] After conversion to EPSG:4326: {gdf_wgs84.geometry.iloc[0] if len(gdf_wgs84) > 0 else 'No geometries'}"
    )

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
            "properties": clean_props,
        }
        clean_features.append(clean_feature)

    gdf = gpd.GeoDataFrame.from_features(
        {"type": "FeatureCollection", "features": clean_features}, crs=crs
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
        return {key: make_json_serializable(item) for key, item in value.items()}

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
                "id_field": (
                    MODEL_STORE["uploaded_layers"]["hydrants"].get("id_field")
                    if MODEL_STORE["uploaded_layers"]["hydrants"]
                    else None
                ),
                "fields": (
                    MODEL_STORE["uploaded_layers"]["hydrants"].get("fields", [])
                    if MODEL_STORE["uploaded_layers"]["hydrants"]
                    else []
                ),
            },
            "valves": {
                "id_field": (
                    MODEL_STORE["uploaded_layers"]["valves"].get("id_field")
                    if MODEL_STORE["uploaded_layers"]["valves"]
                    else None
                ),
                "fields": (
                    MODEL_STORE["uploaded_layers"]["valves"].get("fields", [])
                    if MODEL_STORE["uploaded_layers"]["valves"]
                    else []
                ),
            },
            "flushing_zones": {
                "fields": (MODEL_STORE["uploaded_layers"].get("flushing_zones") or {}).get("fields", []),
                "label_field": (MODEL_STORE["uploaded_layers"].get("flushing_zones") or {}).get("label_field"),
                "labels_visible": (MODEL_STORE["uploaded_layers"].get("flushing_zones") or {}).get("labels_visible", False),
            },
        },
        "element_mapping": MODEL_STORE.get("element_mapping", {}),
        "connection_options": MODEL_STORE.get("connection_options", {}),
        "flush_options": MODEL_STORE.get("flush_options", {}),
        "valve_snap_distance_ft": MODEL_STORE.get("valve_snap_distance_ft", 120.0),
        "sequences": [
            sequence.get("name") for sequence in MODEL_STORE.get("sequences", [])
        ],
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("meta.json", json.dumps(project_meta))
        archive.writestr(
            "model.pkl",
            pickle.dumps(MODEL_STORE["wn"], protocol=pickle.HIGHEST_PROTOCOL),
        )
        archive.writestr(
            "sequences.json",
            json.dumps(MODEL_STORE.get("sequences", []), allow_nan=False),
        )

        model_dir = MODEL_STORE.get("model_dir") or os.path.dirname(
            MODEL_STORE.get("inp_path") or ""
        )
        if not model_dir:
            model_dir = tempfile.mkdtemp(
                prefix="flushing_journal_project_",
                dir=app.config["UPLOAD_FOLDER"],
            )
        os.makedirs(model_dir, exist_ok=True)

        base_inp_path = MODEL_STORE.get("inp_path")
        expected_base_inp_path = os.path.join(model_dir, "BaseModel.inp")
        if (
            not base_inp_path
            or not os.path.exists(base_inp_path)
            or os.path.abspath(base_inp_path)
            != os.path.abspath(expected_base_inp_path)
        ):
            base_inp_path = expected_base_inp_path
            wntr.network.write_inpfile(MODEL_STORE["wn"], base_inp_path)
            set_model_paths(base_inp_path)

        MODEL_STORE["model_dir"] = model_dir
        with open(base_inp_path, "rb") as inp_file:
            archive.writestr("inpFiles/BaseModel.inp", inp_file.read())

        for generated_inp_path in MODEL_STORE.get("generated_inp_files", []):
            if (
                generated_inp_path
                and os.path.isfile(generated_inp_path)
                and os.path.abspath(os.path.dirname(generated_inp_path))
                == os.path.abspath(model_dir)
            ):
                with open(generated_inp_path, "rb") as inp_file:
                    archive.writestr(
                        os.path.join(
                            "inpFiles",
                            os.path.basename(generated_inp_path),
                        ).replace(os.sep, "/"),
                        inp_file.read(),
                    )

        results_path = MODEL_STORE.get("results_path")
        if (
            results_path
            and os.path.isfile(results_path)
            and os.path.abspath(os.path.dirname(results_path))
            == os.path.abspath(model_dir)
        ):
            with open(results_path, "r", encoding="utf-8") as results_file:
                archive.writestr("results.txt", results_file.read())

        for layer_name in ["hydrants", "valves", "flushing_zones"]:
            layer = MODEL_STORE["uploaded_layers"].get(layer_name)
            if layer and layer.get("geojson"):
                archive.writestr(f"{layer_name}.geojson", json.dumps(layer["geojson"]))

        for sequence in MODEL_STORE.get("sequences", []):
            sequence_filename = sanitize_sequence_filename(
                sequence.get("name", "sequence")
            )
            archive.writestr(
                f"sequences/{sequence_filename}", sequence_to_text(sequence)
            )

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
        project_dir = tempfile.mkdtemp(
            prefix="flushing_journal_project_",
            dir=app.config["UPLOAD_FOLDER"],
        )
        inp_members = [
            member_name
            for member_name in archive.namelist()
            if member_name.lower().endswith(".inp")
        ]
        base_member = next(
            (
                member_name
                for member_name in inp_members
                if os.path.basename(member_name).lower() == "basemodel.inp"
            ),
            None,
        )
        if base_member is None:
            base_member = next(
                (
                    member_name
                    for member_name in inp_members
                    if os.path.basename(member_name).lower() == "model.inp"
                ),
                None,
            )

        inp_path = None
        generated_inp_files = []
        extracted_names = set()
        for member_name in inp_members:
            basename = os.path.basename(member_name)
            if not basename or basename in extracted_names:
                continue
            if member_name == base_member:
                destination_name = "BaseModel.inp"
            else:
                destination_name = basename

            destination_path = os.path.join(project_dir, destination_name)
            with open(destination_path, "wb") as inp_file:
                inp_file.write(archive.read(member_name))
            extracted_names.add(destination_name)

            if destination_name == "BaseModel.inp":
                inp_path = destination_path
            else:
                generated_inp_files.append(destination_path)

        if "model.pkl" in archive.namelist():
            wn = pickle.loads(archive.read("model.pkl"))

        if wn is None and inp_path:
            wn = wntr.network.WaterNetworkModel(inp_path)

        if wn is None:
            raise ValueError("Uploaded project archive does not contain a valid model.")

        if inp_path is None:
            inp_path = os.path.join(project_dir, "BaseModel.inp")
            wntr.network.write_inpfile(wn, inp_path)
        elif base_member:
            wn.options.hydraulic.pattern = None
            wntr.network.write_inpfile(wn, inp_path)

        MODEL_STORE["wn"] = wn
        set_model_paths(inp_path)
        MODEL_STORE["model_dir"] = project_dir
        MODEL_STORE["generated_inp_files"] = generated_inp_files
        results_member = next(
            (
                member_name
                for member_name in archive.namelist()
                if member_name.lower() in {"results.txt", "results/results.txt"}
            ),
            None,
        )
        results_dict = {}
        results_path = None
        if results_member:
            results_dict = json.loads(
                archive.read(results_member).decode("utf-8")
            )
            if not isinstance(results_dict, dict):
                raise ValueError("Project results file must contain a JSON object.")
            results_path = os.path.join(project_dir, "results.txt")
            with open(results_path, "w", encoding="utf-8") as results_file:
                json.dump(results_dict, results_file, indent=2, allow_nan=False)
        MODEL_STORE["results_dict"] = results_dict
        MODEL_STORE["results_path"] = results_path
        MODEL_STORE["model_crs"] = model_crs
        MODEL_STORE["pipe_geojson"] = water_network_pipes_to_geojson(
            wn=wn, model_crs=model_crs
        )
        MODEL_STORE["connection_options"] = {
            "lateral_diameter_in": 5.99,
            "lateral_roughness": 1.0,
            "search_distance_ft": 120.0,
        }
        MODEL_STORE["flush_options"] = {
            "model_timestep": 0,
            "default_orifice_diam": 2.5,
            "volume_turnovers": 3.0,
            "pipes_to_reflush": 1,
            "min_flush_vel": 5.0,
            "start_vel_to_flushing_vel_ratio": 3.0,
        }
        MODEL_STORE["valve_snap_distance_ft"] = 120.0
        saved_connection_options = meta.get("connection_options")
        if isinstance(saved_connection_options, dict):
            MODEL_STORE["connection_options"] = {
                **MODEL_STORE["connection_options"],
                **saved_connection_options,
            }
        saved_flush_options = meta.get("flush_options")
        if isinstance(saved_flush_options, dict):
            MODEL_STORE["flush_options"] = {
                **MODEL_STORE["flush_options"],
                **saved_flush_options,
            }
        try:
            saved_snap_distance = float(meta.get("valve_snap_distance_ft", 120.0))
        except (TypeError, ValueError):
            saved_snap_distance = 120.0
        if math.isfinite(saved_snap_distance) and saved_snap_distance >= 0:
            MODEL_STORE["valve_snap_distance_ft"] = saved_snap_distance

        for layer_name in ["hydrants", "valves"]:
            if f"{layer_name}.geojson" in archive.namelist():
                geojson = json.loads(
                    archive.read(f"{layer_name}.geojson").decode("utf-8")
                )
                geojson_field_names = sorted(
                    {
                        key
                        for feature in geojson.get("features", [])
                        for key in (feature.get("properties") or {}).keys()
                    }
                )
                layer_meta = meta.get("uploaded_layers", {}).get(layer_name, {})
                saved_fields = layer_meta.get("fields")
                if (
                    isinstance(saved_fields, list)
                    and all(isinstance(field_name, str) for field_name in saved_fields)
                ):
                    field_names = list(saved_fields)
                else:
                    generated_fields = {
                        "model_elements",
                        "original_location",
                        "hydrant_junction_name",
                        "connection_node_name",
                        "hydrant_pipe_name",
                        "model_pipe_name",
                        "model_pipe_nodes",
                    }
                    field_names = [
                        field_name
                        for field_name in geojson_field_names
                        if field_name not in generated_fields
                    ]

                id_field = layer_meta.get("id_field")
                if id_field not in field_names:
                    id_field = None

                MODEL_STORE["uploaded_layers"][layer_name] = {
                    "path": None,
                    "geojson": geojson,
                    "shape_name": f"{layer_name}.geojson",
                    "fields": field_names,
                    "id_field": id_field,
                }
            else:
                MODEL_STORE["uploaded_layers"][layer_name] = None

        if "flushing_zones.geojson" in archive.namelist():
            zones_geojson = json.loads(archive.read("flushing_zones.geojson").decode("utf-8"))
            zones_meta = meta.get("uploaded_layers", {}).get("flushing_zones", {})
            zones_fields = zones_meta.get("fields")
            if not isinstance(zones_fields, list):
                zones_fields = sorted({key for feature in zones_geojson.get("features", []) for key in (feature.get("properties") or {})})
            label_field = zones_meta.get("label_field")
            if label_field not in zones_fields:
                label_field = None
            MODEL_STORE["uploaded_layers"]["flushing_zones"] = {"path": None, "geojson": zones_geojson, "shape_name": "flushing_zones.geojson", "fields": zones_fields, "label_field": label_field, "labels_visible": bool(zones_meta.get("labels_visible", False))}
        else:
            MODEL_STORE["uploaded_layers"]["flushing_zones"] = None

        sequences = []
        if "sequences.json" in archive.namelist():
            sequences = json.loads(
                archive.read("sequences.json").decode("utf-8")
            )
            if not isinstance(sequences, list) or any(
                not isinstance(sequence, dict)
                or not isinstance(sequence.get("operations"), list)
                for sequence in sequences
            ):
                raise ValueError(
                    "Project sequences file must contain a list of sequences with operations."
                )
        else:
            for member_name in archive.namelist():
                if member_name.lower().startswith(
                    "sequences/"
                ) and member_name.lower().endswith(".txt"):
                    text = archive.read(member_name).decode("utf-8")
                    sequences.append(
                        parse_sequence_text(text, os.path.basename(member_name))
                    )

        MODEL_STORE["sequences"] = sequences

        saved_mapping = meta.get("element_mapping")
        if isinstance(saved_mapping, dict) and all(
            isinstance(saved_mapping.get(kind, {}), dict)
            and all(isinstance(value, str) for value in saved_mapping.get(kind, {}).values())
            for kind in ("hydrants", "valves")
        ):
            MODEL_STORE["element_mapping"] = {
                "hydrants": saved_mapping.get("hydrants", {}),
                "valves": saved_mapping.get("valves", {}),
            }
        else:
            _restore_element_mapping_from_layers()

        return {
            "model_crs": model_crs,
            "pipe_geojson": MODEL_STORE["pipe_geojson"],
            "hydrants": get_uploaded_layer_response(
                MODEL_STORE["uploaded_layers"]["hydrants"]
            ),
            "valves": get_uploaded_layer_response(
                MODEL_STORE["uploaded_layers"]["valves"]
            ),
            "flushing_zones": ({"geojson": MODEL_STORE["uploaded_layers"]["flushing_zones"]["geojson"], "fields": MODEL_STORE["uploaded_layers"]["flushing_zones"]["fields"], "label_field": MODEL_STORE["uploaded_layers"]["flushing_zones"].get("label_field"), "labels_visible": MODEL_STORE["uploaded_layers"]["flushing_zones"].get("labels_visible", False)} if MODEL_STORE["uploaded_layers"].get("flushing_zones") else None),
            "sequences": sequences,
            "results_dict": results_dict,
            "options": {
                "connection_options": MODEL_STORE.get("connection_options", {}),
                "flush_options": MODEL_STORE.get("flush_options", {}),
                "valve_snap_distance_ft": MODEL_STORE.get(
                    "valve_snap_distance_ft", 120.0
                ),
            },
        }


def send_project_archive():
    archive_buffer = create_project_archive()
    return send_file(
        archive_buffer,
        mimetype="application/zip",
        as_attachment=True,
        download_name="flushing_journal_project.zip",
    )


def get_uploaded_layer_response(layer):
    if not layer:
        return None

    return {
        "geojson": layer["geojson"],
        "fields": layer["fields"],
        "selected_id_field": layer.get("id_field"),
    }


def make_project_response():
    return {
        "success": True,
        "model_crs": MODEL_STORE["model_crs"],
        "pipe_geojson": MODEL_STORE["pipe_geojson"],
        "hydrants": get_uploaded_layer_response(
            MODEL_STORE["uploaded_layers"]["hydrants"]
        ),
        "valves": get_uploaded_layer_response(MODEL_STORE["uploaded_layers"]["valves"]),
        "sequences": MODEL_STORE.get("sequences", []),
        "results_dict": MODEL_STORE.get("results_dict", {}),
        "element_mapping": MODEL_STORE.get("element_mapping", {}),
        "options": {
            "connection_options": MODEL_STORE.get("connection_options", {}),
            "flush_options": MODEL_STORE.get("flush_options", {}),
            "valve_snap_distance_ft": MODEL_STORE.get(
                "valve_snap_distance_ft", 120.0
            ),
        },
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
    new_path = os.path.join(
        app.config["UPLOAD_FOLDER"], f"project_model_{uuid.uuid4().hex}.inp"
    )
    wntr.network.write_inpfile(wn, new_path)
    return new_path


def get_project_error_response(exc):
    return jsonify({"success": False, "message": str(exc)}), 400


def restore_project_from_file(project_zip):
    return restore_project_archive(project_zip)


def get_project_layer_data(layer_name):
    layer = MODEL_STORE["uploaded_layers"].get(layer_name)
    if not layer:
        return None
    return {
        "geojson": layer["geojson"],
        "fields": layer["fields"],
        "selected_id_field": layer.get("id_field"),
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

    transformer = Transformer.from_crs(model_crs_text, "EPSG:4326", always_xy=True)

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
                "status": str(getattr(pipe, "status", "")),
            },
            "geometry": {"type": "LineString", "coordinates": transformed_coords},
        }

        features.append(feature)

    return make_json_serializable({"type": "FeatureCollection", "features": features})


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
