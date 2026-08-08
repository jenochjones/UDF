from datetime import date, datetime
from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.utils import secure_filename
from pyproj import CRS, Transformer
import wntr
import geopandas as gpd
import json
import math
import os
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
    }
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

        MODEL_STORE["wn"] = wn
        MODEL_STORE["inp_path"] = inp_path
        MODEL_STORE["model_crs"] = model_crs
        MODEL_STORE["pipe_geojson"] = pipe_geojson

        return jsonify({
            "success": True,
            "message": "Model loaded successfully.",
            "model_crs": model_crs,
            "pipe_count": len(pipe_geojson["features"]),
            "pipe_geojson": pipe_geojson
        })

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
            "valves": result["valves"]
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
    """
    Connect each uploaded hydrant to the nearest pipe in the loaded WNTR model.
    """

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
        print('converting to geojson')
        geojson, field_names = point_shapefile_to_geojson(
            shp_path=shp_path,
            source_crs=source_crs_value or None
        )

        if selected_id_field and selected_id_field not in field_names:
            selected_id_field = None

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


def point_shapefile_to_geojson(shp_path, source_crs=None):
    """
    Read a point shapefile and convert it to GeoJSON in EPSG:4326.
    """

    if not os.path.exists(shp_path):
        raise ValueError("Shapefile was not found on disk.")

    gdf = gpd.read_file(shp_path)
    
    print(f"[DEBUG] Shapefile loaded. Current CRS: {gdf.crs}")
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
        }
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

        return {
            "model_crs": model_crs,
            "pipe_geojson": MODEL_STORE["pipe_geojson"],
            "hydrants": MODEL_STORE["uploaded_layers"]["hydrants"],
            "valves": MODEL_STORE["uploaded_layers"]["valves"]
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
        "valves": get_uploaded_layer_response(MODEL_STORE["uploaded_layers"]["valves"])
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

        feature = {
            "type": "Feature",
            "properties": {
                "id": pipe_name,
                "name": pipe_name,
                "start_node": pipe.start_node_name,
                "end_node": pipe.end_node_name,
                "length": safe_float(getattr(pipe, "length", None)),
                "diameter": safe_float(getattr(pipe, "diameter", None)),
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