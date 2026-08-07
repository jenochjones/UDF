from datetime import date, datetime
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from pyproj import CRS, Transformer
import wntr
import geopandas as gpd
import json
import os
import tempfile
import traceback
import uuid
from shapely.geometry import shape, Point


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


@app.route("/connect_hydrants", methods=["POST"])
def connect_hydrants():
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
        pipe_features = MODEL_STORE["pipe_geojson"]["features"]

        transformer_to_model = Transformer.from_crs(
            "EPSG:4326",
            model_crs,
            always_xy=True
        )

        hydrant_id_field = hydrants_layer.get("id_field")

        for hydrant_feature in hydrant_features:
            geometry = hydrant_feature.get("geometry")
            if not geometry:
                continue

            hydrant_id = hydrant_feature.get("properties", {}).get(hydrant_id_field) if hydrant_id_field else None
            hydrant_junction_name = hydrant_id if hydrant_id else f"HYDRANT-{uuid.uuid4().hex[:8]}"
            
            hydrant_point_4326 = shape(geometry)
            nearest_pipe_feature = min(
                pipe_features,
                key=lambda feature: hydrant_point_4326.distance(shape(feature["geometry"]))
            )
            nearest_line = shape(nearest_pipe_feature["geometry"])
            nearest_point_4326 = nearest_line.interpolate(
                nearest_line.project(hydrant_point_4326)
            )

            pipe_name = nearest_pipe_feature["properties"]["id"]
            pipe = wn.get_link(pipe_name)
            if pipe is None:
                continue

            start_node = pipe.start_node_name
            end_node = pipe.end_node_name
            start_coords = getattr(wn.get_node(start_node), "coordinates", None)
            end_coords = getattr(wn.get_node(end_node), "coordinates", None)

            if start_coords is None or end_coords is None:
                raise ValueError(
                    f"Pipe '{pipe_name}' does not have endpoint coordinates."
                )

            x_hyd, y_hyd = transformer_to_model.transform(
                hydrant_point_4326.x,
                hydrant_point_4326.y
            )
            x_split, y_split = transformer_to_model.transform(
                nearest_point_4326.x,
                nearest_point_4326.y
            )

            connection_junction_name = f"{hydrant_junction_name}-CONN"

            start_pt = Point(start_coords)
            end_pt = Point(end_coords)
            split_pt = Point(x_split, y_split)

            if split_pt.distance(start_pt) < 1e-6:
                connection_node = start_node
                split_pipe = False
            elif split_pt.distance(end_pt) < 1e-6:
                connection_node = end_node
                split_pipe = False
            else:
                connection_node = connection_junction_name
                split_pipe = True

            if split_pipe:
                pipe_length = wn.get_link(pipe_name).length
                split_distance = float(split_pt.distance(start_pt)) / pipe_length

                print(f"Splitting pipe '{pipe_name}' at {split_distance:.4f} fraction of its length.")
                wn = wntr.morph.split_pipe(wn, pipe_name_to_split=pipe_name, new_pipe_name=f"{pipe_name}_{uuid.uuid4().hex[:6]}", new_junction_name=hydrant_junction_name, split_at_point=0.5)#split_distance)

                hyd_elev = wn.get_node(hydrant_junction_name).elevation

                wn.add_junction(
                    hydrant_junction_name,
                    base_demand=0.0,
                    elevation=hyd_elev,
                    coordinates=(x_hyd, y_hyd)
                )

            hydrant_pipe_name = f"{hydrant_junction_name}_pipe_{uuid.uuid4().hex[:6]}"
            hydrant_pipe_length = float(split_pt.distance(Point(x_hyd, y_hyd)))

            wn.add_pipe(
                hydrant_pipe_name,
                hydrant_junction_name,
                connection_node,
                length=hydrant_pipe_length,
                diameter=0.1524,
                roughness=100.0,
                minor_loss=0.0,
                initial_status="OPEN"
            )

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

    if gdf.empty:
        return {
            "type": "FeatureCollection",
            "features": []
        }, []

    geometry_types = {geom_type.lower() for geom_type in gdf.geom_type.unique()}
    if not geometry_types.issubset({"point", "multipoint"}):
        raise ValueError("Only point shapefiles are supported for this workflow.")

    if gdf.crs is None:
        if source_crs:
            gdf = gdf.set_crs(source_crs, allow_override=True)
        else:
            gdf = gdf.set_crs("EPSG:4326", allow_override=True)
    elif source_crs and gdf.crs.to_string().lower() != source_crs.lower():
        gdf = gdf.set_crs(source_crs, allow_override=True)

    field_names = [col for col in gdf.columns if col.lower() != "geometry"]
    gdf_wgs84 = gdf.to_crs("EPSG:4326")

    for col in gdf_wgs84.columns:
        if gdf_wgs84[col].dtype != "str" and gdf_wgs84[col].dtype != "geometry":
            gdf_wgs84[col] = gdf_wgs84[col].astype(str)
            
    geojson = json.loads(gdf_wgs84.to_json())

    return geojson, field_names


def make_json_serializable(value):
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

    if isinstance(value, (str, int, float, bool)) or value is None:
        return value

    return str(value)


def water_network_pipes_to_geojson(wn, model_crs):
    """
    Convert WNTR pipe links to Leaflet-friendly GeoJSON in EPSG:4326.

    Assumes WNTR node coordinates are in the CRS provided by model_crs.
    Leaflet expects GeoJSON coordinates as [longitude, latitude].
    """

    transformer = Transformer.from_crs(
        model_crs,
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

        x1, y1 = start_coords
        x2, y2 = end_coords

        lon1, lat1 = transformer.transform(x1, y1)
        lon2, lat2 = transformer.transform(x2, y2)

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
                "coordinates": [
                    [lon1, lat1],
                    [lon2, lat2]
                ]
            }
        }

        features.append(feature)

    return {
        "type": "FeatureCollection",
        "features": features
    }


def safe_float(value):
    """
    Convert numpy/pandas/scalar values to normal JSON-safe floats.
    """

    if value is None:
        return None

    try:
        return float(value)
    except Exception:
        return None


if __name__ == "__main__":
    # Spyder-friendly: hard-coded host/port, no argparse
    app.run(host="127.0.0.1", port=5000, debug=True)