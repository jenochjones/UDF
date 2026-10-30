"""
GIS_MAPPING.py - ArcGIS Pro script tool that builds one flushing map + layout per
flushing operation from an exported flushing_journal_project zip file.

Run inside the flushing templates project (ArcGIS Pro -> Script tool, or from the
Python window / notebook of the open project).

Tool parameters (in order):
    0  Flushing journal project zip (File, required)
    1  Extent buffer in map units (Double, optional, default 300)
    2  Minimum map scale (Double, optional, default 1000)
    3  PDF output folder (Folder, optional; layouts are exported when given)

Expected zip contents: sequences.json, hydrants.geojson, valves.geojson, meta.json,
inpFiles/BaseModel.inp, and optionally results.txt (JSON results dictionary) and
flushing_zones.geojson (shown on the sequence overview maps).
One map + layout is created per operation, plus a "<sequence>-Overview" map + layout per sequence.
The template project must contain at least one map and one layout. The first of
each is copied for every operation.
"""
import json
import colorsys
import math
import os
import re
import sys
import zipfile

import arcpy

BASE_INP = 'inpFiles/BaseModel.inp'
OVERVIEW_MAP_TEMPLATE = 'LayersOverview'
OVERVIEW_LAYOUT_TEMPLATE = 'FlushingJournalOverviewTemplate'
HYD_STATUS_FLD, HYD_MIN_FLD, TIME_FLD = 'STATUS', 'MINUTES', 'TIME'
SYMBOLOGY = {  # layers in the project that hold the symbology
    'valves': 'ValvesSymbology',
    'hydrants': 'HydrantSymbology',
    'pipes': 'PipeSymbology',
}


def get_param(index, default=None):
    """Value of tool parameter `index`; blank optional parameters (empty or '#') give `default`."""
    value = ''
    if arcpy.GetArgumentCount() > index:
        value = arcpy.GetParameterAsText(index)
    elif len(sys.argv) > index + 1:
        value = sys.argv[index + 1]
    value = (value or '').strip()
    return default if value in ('', '#') else value


def message(text):
    arcpy.AddMessage(text)


def warn(text):
    arcpy.AddWarning(text)


def safe_name(text):
    return re.sub(r'\W', '_', str(text))


# ---------------------------------------------------------------- zip loading
def load_zip(zip_path):
    """Reads the project zip the same way the Flask app does (restore_project_archive)."""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        lower = {n.lower(): n for n in names}
        for required in ('sequences.json', 'hydrants.geojson', 'valves.geojson'):
            if required not in names:
                raise ValueError(f'{required} not found in {zip_path}')
        inps = [n for n in names if n.lower().endswith('.inp')]
        base = next((n for n in inps if os.path.basename(n).lower() == 'basemodel.inp'), None) or \
            next((n for n in inps if os.path.basename(n).lower() == 'model.inp'), None)
        if base is None:
            raise ValueError(f'{BASE_INP} not found in {zip_path}')
        results_name = next((lower[k] for k in ('results.txt', 'results/results.txt') if k in lower), None)
        results = json.loads(z.read(results_name).decode('utf-8')) if results_name else {}
        sequences = json.loads(z.read('sequences.json').decode('utf-8'))
        hydrants = json.loads(z.read('hydrants.geojson').decode('utf-8'))
        valves = json.loads(z.read('valves.geojson').decode('utf-8'))
        inp_text = z.read(base).decode('latin1')
        # operation inp files are written from the sequence network and are used as a pipe fallback
        op_inps = {os.path.basename(n): z.read(n).decode('latin1') for n in inps if n != base}
        meta = json.loads(z.read('meta.json').decode('utf-8')) if 'meta.json' in names else {}
        zones = json.loads(z.read('flushing_zones.geojson').decode('utf-8')) if 'flushing_zones.geojson' in names else None
    return results, sequences, hydrants, valves, inp_text, meta, op_inps, zones


def feature_id(props, id_field):
    """GIS id used by the sequences: the layer's id field chosen in the app (ASSETID as fallback)."""
    for field in (id_field, 'ASSETID'):
        if field and props.get(field) is not None and str(props[field]).strip():
            return str(props[field]).strip()
    return None


def build_mapping(meta, gj, kind, id_field):
    """GIS id -> model element (hydrant junction / valve pipe), same as the app's element_mapping."""
    saved = (meta.get('element_mapping') or {}).get(kind)
    if isinstance(saved, dict) and saved:
        return {str(k): str(v) for k, v in saved.items()}
    mapping = {}
    for f in gj['features']:
        p = f.get('properties') or {}
        gid = feature_id(p, id_field)
        me = p.get('model_elements') or {}
        if kind == 'hydrants':
            name = me.get('node') or p.get('hydrant_junction_name')
        else:
            name = me.get('pipe') or p.get('model_pipe_name')
        if gid and name:
            mapping[gid] = str(name)
    return mapping


def inp_sections(text):
    sections, current = {}, None
    for line in text.splitlines():
        line = line.split(';')[0].strip()
        if not line:
            continue
        if line.startswith('['):
            current = line.strip('[]').upper()
            sections[current] = []
        elif current:
            sections[current].append(line.split())
    return sections


def pipe_geometry_table(inp_text):
    """Returns {pipe_id: [(x, y), ...]} using node coordinates and vertices from the base model."""
    sections = inp_sections(inp_text)
    coords = {r[0]: (float(r[1]), float(r[2])) for r in sections.get('COORDINATES', []) if len(r) >= 3}
    verts = {}
    for r in sections.get('VERTICES', []):
        if len(r) >= 3:
            verts.setdefault(r[0], []).append((float(r[1]), float(r[2])))
    lines = {}
    for r in sections.get('PIPES', []):
        pid, n1, n2 = r[0], r[1], r[2]
        if n1 in coords and n2 in coords:
            lines[pid] = [coords[n1]] + verts.get(pid, []) + [coords[n2]]
    return lines


INTERSECTION_FT = 20.0
CARDINALS = ['north', 'east', 'south', 'west']


def intersection_nodes(inp_text, hydrant_nodes=()):
    """Returns {node: (x, y)} for model nodes where three or more pipes meet, ignoring pipes
    connected directly to hydrant junctions."""
    sections = inp_sections(inp_text)
    coords = {r[0]: (float(r[1]), float(r[2])) for r in sections.get('COORDINATES', []) if len(r) >= 3}
    hydrant_nodes = set(hydrant_nodes)
    degree = {}
    for r in sections.get('PIPES', []):
        if r[1] in hydrant_nodes or r[2] in hydrant_nodes:
            continue
        for n in r[1:3]:
            degree[n] = degree.get(n, 0) + 1
    return {n: coords[n] for n, d in degree.items() if d >= 3 and n in coords}


def valve_leg_note(valve_geom, model_sr, intersections):
    """'({direction} leg)' when the valve is within 20 ft of a pipe intersection, else ''."""
    pt = valve_geom.projectAs(model_sr).firstPoint
    to_ft = model_sr.metersPerUnit / 0.3048
    best, best_d = None, None
    for x, y in intersections.values():
        d = math.hypot(pt.X - x, pt.Y - y) * to_ft
        if best_d is None or d < best_d:
            best, best_d = (x, y), d
    if best is None or best_d > INTERSECTION_FT:
        return ''
    bearing = math.degrees(math.atan2(pt.X - best[0], pt.Y - best[1])) % 360
    return f'({CARDINALS[int(round(bearing / 90.0)) % 4]} leg)'


# ---------------------------------------------------------------- feature classes
def new_fc(gdb, name, geom_type, sr, fields):
    path = os.path.join(gdb, name)
    if arcpy.Exists(path):
        arcpy.management.Delete(path)
    arcpy.management.CreateFeatureclass(gdb, name, geom_type, spatial_reference=sr)
    for fname, ftype, length in fields:
        if length:
            arcpy.management.AddField(path, fname, ftype, field_length=length)
        else:
            arcpy.management.AddField(path, fname, ftype)
    return path


PIPE_FIELDS = [('EPANET_ID', 'TEXT', 40), ('STATUS', 'TEXT', 30), ('SEQUENCE', 'TEXT', 20),
               ('VELOCITY', 'TEXT', 10), ('HYDRANTID', 'TEXT', 20), (TIME_FLD, 'TEXT', 30),
               ('OPERATION', 'TEXT', 30)]
HYDRANT_FIELDS = [('ASSETID', 'TEXT', 30), (HYD_STATUS_FLD, 'TEXT', 30), (HYD_MIN_FLD, 'TEXT', 30), (TIME_FLD, 'TEXT', 30)]
VALVE_FIELDS = [('ASSETID', 'TEXT', 30), ('STATUS', 'TEXT', 30), ('FL_LABEL', 'TEXT', 30), (TIME_FLD, 'TEXT', 30),
                ('NOTE', 'TEXT', 60)]


def copy_with_status(base_fc, out_fc, fields, row_values, keep_only_set=False):
    """Copies base_fc and sets `fields` (first one is the id) for rows where row_values(row) is not None.
    With keep_only_set, rows where row_values returns None are removed from the copy."""
    arcpy.management.CopyFeatures(base_fc, out_fc)
    with arcpy.da.UpdateCursor(out_fc, fields) as cur:
        for row in cur:
            new = row_values(row)
            if new is not None:
                cur.updateRow(new)
            elif keep_only_set:
                cur.deleteRow()
    return out_fc


def build_zones_fc(gdb, zones_gj, sr):
    """Flushing zone polygons from flushing_zones.geojson (EPSG:4326)."""
    path = new_fc(gdb, 'Flushing_Zones', 'POLYGON', sr, [('ZONE', 'TEXT', 60)])
    with arcpy.da.InsertCursor(path, ['SHAPE@', 'ZONE']) as cur:
        for f in zones_gj.get('features', []):
            geom = f.get('geometry')
            if not geom:
                continue
            props = f.get('properties') or {}
            try:
                shape = arcpy.AsShape(geom, False)
            except Exception as exc:
                warn(f'Skipping a flushing zone with unreadable geometry ({exc})')
                continue
            cur.insertRow([shape, str(props.get('ZONE') or props.get('Name') or '')[:60]])
    return path


def style_zones(layer):
    """Black borders with a transparent fill."""
    sym = layer.symbology
    sym.updateRenderer('SimpleRenderer')
    symbol = sym.renderer.symbol
    symbol.color = {'RGB': [0, 0, 0, 0]}
    symbol.outlineColor = {'RGB': [0, 0, 0, 100]}
    symbol.outlineWidth = 1.5
    layer.symbology = sym
    layer.showLabels = False


def operation_colors(count):
    """Distinct RGB colors, one per operation."""
    colors = []
    for i in range(count):
        h = (i * 0.618033988749895) % 1.0  # golden-ratio hue steps keep neighbours distinct
        s, v = (0.85, 0.9) if i % 2 == 0 else (0.7, 0.7)
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        colors.append([int(r * 255), int(g * 255), int(b * 255), 100])
    return colors


def style_pipes_by_operation(layer, op_names):
    sym = layer.symbology
    sym.updateRenderer('UniqueValueRenderer')
    sym.renderer.fields = ['OPERATION']
    layer.symbology = sym
    sym = layer.symbology
    colors = dict(zip(op_names, operation_colors(len(op_names))))
    for group in sym.renderer.groups:
        for item in group.items:
            value = str(item.values[0][0]) if item.values and item.values[0] else ''
            if value in colors:
                item.symbol.color = {'RGB': colors[value]}
                item.symbol.size = 3
                item.label = f'Operation {value}'
    layer.symbology = sym
    layer.showLabels = False


# ---------------------------------------------------------------- layout helpers
def set_text(layout, name, text):
    elements = layout.listElements('TEXT_ELEMENT', name)
    if elements:
        elements[0].text = text if text not in (None, '') else ' '


def find_symbology_layers(aprx):
    """Finds the symbology source layers (by name) in any map of the project."""
    found = {}
    for m in aprx.listMaps():
        for lyr in m.listLayers():
            for key, name in SYMBOLOGY.items():
                if lyr.name == name and key not in found:
                    found[key] = lyr
    for key, name in SYMBOLOGY.items():
        if key not in found:
            warn(f'Layer {name} not found in the project; default symbology used')
    return found


def apply_symbology(layer, source, key):
    """Copies the renderer and labels from the symbology layer; falls back to ApplySymbologyFromLayer."""
    if source is None:
        return
    try:
        src_cim = source.getDefinition('V3')
        dst_cim = layer.getDefinition('V3')
        dst_cim.renderer = src_cim.renderer
        if getattr(src_cim, 'labelClasses', None):
            dst_cim.labelClasses = src_cim.labelClasses
        dst_cim.labelVisibility = getattr(src_cim, 'labelVisibility', False)
        layer.setDefinition(dst_cim)
        fields = {f.name.upper() for f in arcpy.ListFields(layer)}
        used = [f for f in (getattr(src_cim.renderer, 'fields', None) or []) if f.upper() not in fields]
        if used:
            warn(f'{key} symbology uses field(s) {used} that are missing from the generated layer')
        return
    except Exception as exc:
        warn(f'Could not copy {key} symbology through the layer definition ({exc}); trying ApplySymbologyFromLayer')
    try:
        arcpy.management.ApplySymbologyFromLayer(layer, source)
    except Exception as exc:
        warn(f'Could not apply {key} symbology: {exc}')


VALVE_LABEL_EXPR = "$feature.ASSETID + IIf(IsEmpty($feature.NOTE), '', ' ' + $feature.NOTE)"


def label_valves(layer):
    layer.showLabels = True
    for lc in layer.listLabelClasses():
        if lc.name == 'Open':
            lc.SQLQuery = "STATUS = 'Reopen'"
            lc.expression = VALVE_LABEL_EXPR
            lc.visible = True
        elif lc.name == 'Closed':
            lc.SQLQuery = "STATUS = 'Close'"
            lc.expression = VALVE_LABEL_EXPR
            lc.visible = True
        else:
            lc.visible = False


def label_hydrants(layer, status='Current Sequence Open'):
    layer.showLabels = True
    lc = layer.listLabelClasses()[0]
    lc.SQLQuery = f"STATUS = '{status}'"
    lc.expression = '$feature.ASSETID'
    lc.visible = True


def copy_item(aprx, kind, template_name, name):
    """Copies the template map/layout. The template is looked up by name each time because
    the object held from earlier in the run can become stale once the project has been modified."""
    def find():
        items = aprx.listMaps() if kind == 'map' else aprx.listLayouts()
        return next(i for i in items if i.name == template_name)
    try:
        return aprx.copyItem(find(), name)
    except RuntimeError as exc:
        warn(f'copyItem failed for {kind} {name} ({exc}); saving the project and retrying')
    aprx.save()
    return aprx.copyItem(find(), name)


def setup_legend(layout, frame, keep_layers, visible_only=False):
    """Keeps only the given layers in the legend(s) of the layout and hides their layer names.
    With visible_only, items only list features inside the map frame extent and headings are off."""
    keep = {l.name for l in keep_layers}
    for legend in layout.listElements('LEGEND_ELEMENT'):
        try:
            legend.mapFrame = frame
        except Exception:
            pass
        for item in list(legend.items):
            if item.name not in keep:
                legend.removeItem(item)
        try:
            cim = legend.getDefinition('V3')
            for item in cim.items:
                item.showLayerName = False
                if visible_only:
                    item.showHeading = False
                    item.showVisibleFeatures = True
            legend.setDefinition(cim)
        except Exception as exc:
            warn(f'Could not hide legend layer names in {layout.name} ({exc})')
        if visible_only:
            for item in legend.items:
                for prop, value in (('showVisibleFeatures', True), ('showHeading', False)):
                    try:
                        setattr(item, prop, value)
                    except Exception as exc:
                        warn(f'Could not set legend {prop} for {item.name} ({exc})')


def relabel_classes(layer, label, key):
    """Gives every legend class of a unique-value layer the same label."""
    try:
        sym = layer.symbology
        for group in sym.renderer.groups:
            for item in group.items:
                item.label = label
        layer.symbology = sym
    except Exception as exc:
        warn(f'Could not relabel {key} legend entries ({exc})')


def dash_effect_class():
    """CIMGeometricEffectDashes lives in different arcpy.cim modules across Pro versions."""
    import importlib
    import arcpy.cim
    cls = getattr(arcpy.cim, 'CIMGeometricEffectDashes', None)
    if cls is not None:
        return cls
    for module_name in ('arcpy.cim.CIMSymbol', 'arcpy.cim.CIMVectorLayers', 'arcpy.cim.GeometricEffects',
                        'arcpy.cim.CIMEffects', 'arcpy.cim.CIMObject'):
        try:
            cls = getattr(importlib.import_module(module_name), 'CIMGeometricEffectDashes', None)
        except ImportError:
            continue
        if cls is not None:
            return cls
    raise ImportError('CIMGeometricEffectDashes was not found in arcpy.cim')


def style_dashed_black_pipes(layer, label, width=3):
    """Single black dashed line symbol labelled `label`."""
    sym = layer.symbology
    sym.updateRenderer('SimpleRenderer')
    symbol = sym.renderer.symbol
    symbol.color = {'RGB': [0, 0, 0, 100]}
    symbol.size = width
    sym.renderer.label = label
    layer.symbology = sym
    try:
        dashes_cls = dash_effect_class()
        cim = layer.getDefinition('V3')
        for sl in cim.renderer.symbol.symbol.symbolLayers:
            if type(sl).__name__ == 'CIMSolidStroke':
                dashes = dashes_cls()
                dashes.dashTemplate = [6, 4]
                dashes.lineDashEnding = 'NoConstraint'
                dashes.offsetAlongLine = 0
                dashes.controlPointEnding = 'NoConstraint'
                sl.width = width
                sl.effects = [dashes]
        layer.setDefinition(cim)
    except Exception as exc:
        warn(f'Could not apply the dashed line effect to the pipes ({exc}); solid black lines used')
    layer.showLabels = False


def delete_existing(aprx, name):
    for m in aprx.listMaps():
        if m.name == name:
            aprx.deleteItem(m)
    for lay in aprx.listLayouts():
        if lay.name == name:
            aprx.deleteItem(lay)


def extent_of(geometries, out_sr):
    xs, ys = [], []
    for g in geometries:
        g = g.projectAs(out_sr) if out_sr and g.spatialReference.factoryCode != out_sr.factoryCode else g
        e = g.extent
        xs += [e.XMin, e.XMax]
        ys += [e.YMin, e.YMax]
    return min(xs), min(ys), max(xs), max(ys)


def overview_name(seq_name):
    return f'{seq_name}-Overview'


def build_overview(aprx, seq_name, pipe_op, op_order, hyds, valves, notes, base, cfg,
                   pipe_geom, hyd_geom, val_geom, totals):
    """One overview map + layout per sequence, copied from the LayerOverview map and the
    FlushingJournalOverviewTemplate layout. Returns the number of maps created."""
    name = overview_name(seq_name)
    tag = safe_name(name)
    gdb = cfg['gdb']

    all_pipes_fc = copy_with_status(
        base['pipes_base'], os.path.join(gdb, f'PipesAll_{tag}'), ['EPANET_ID', 'STATUS', 'SEQUENCE'],
        lambda r: [r[0], 'Flushed', seq_name] if r[0] in pipe_op else None)
    pipes_fc = copy_with_status(
        base['pipes_base'], os.path.join(gdb, f'Pipes_{tag}'), ['EPANET_ID', 'STATUS', 'SEQUENCE', 'OPERATION'],
        lambda r: [r[0], 'Flushed', seq_name, pipe_op[r[0]]] if r[0] in pipe_op else None, keep_only_set=True)
    hyd_fc = copy_with_status(
        base['hyds_base'], os.path.join(gdb, f'Hydrants_{tag}'), ['ASSETID', HYD_STATUS_FLD],
        lambda r: [r[0], 'Flushed'] if r[0] in hyds else None, keep_only_set=True)
    val_fc = copy_with_status(
        base['vals_base'], os.path.join(gdb, f'Valves_{tag}'), ['ASSETID', 'STATUS', 'NOTE'],
        lambda r: [r[0], 'Reopen', notes.get(r[0])] if r[0] in valves else None, keep_only_set=True)

    delete_existing(aprx, name)
    ov_map = copy_item(aprx, 'map', cfg['overview_map_name'], name)
    zone_layer = ov_map.addDataFromPath(base['zones_fc']) if base['zones_fc'] else None
    all_pipe_layer = ov_map.addDataFromPath(all_pipes_fc)
    flushed_layer = ov_map.addDataFromPath(pipes_fc)
    valve_layer = ov_map.addDataFromPath(val_fc)
    hyd_layer = ov_map.addDataFromPath(hyd_fc)
    symb = cfg['symb_layers']
    apply_symbology(all_pipe_layer, symb.get('pipes'), 'pipes')
    apply_symbology(valve_layer, symb.get('valves'), 'valves')
    apply_symbology(hyd_layer, symb.get('hydrants'), 'hydrants')
    style_dashed_black_pipes(all_pipe_layer, 'Pipes')
    relabel_classes(valve_layer, 'Operated Valves', 'valves')
    relabel_classes(hyd_layer, 'Flushed Hydrants', 'hydrants')
    style_pipes_by_operation(flushed_layer, op_order)
    if zone_layer is not None:
        style_zones(zone_layer)
        zone_layer.name = 'Flushing Zones'
    all_pipe_layer.name, flushed_layer.name = 'Pipes', 'Flushed Pipes'
    valve_layer.name, hyd_layer.name = 'Valves', 'Hydrants'
    all_pipe_layer.showLabels = False
    for lyr in ov_map.listLayers():
        if lyr.name in SYMBOLOGY.values():
            ov_map.removeLayer(lyr)
    label_valves(valve_layer)
    label_hydrants(hyd_layer, 'Flushed')

    layout = copy_item(aprx, 'layout', cfg['overview_layout_name'], name)
    frame = layout.listElements('MAPFRAME_ELEMENT')[0]
    frame.map = ov_map
    # the colored flushed-pipes layer is intentionally left out of the legend
    keep = [l for l in (all_pipe_layer, valve_layer, hyd_layer, zone_layer) if l is not None]
    set_text(layout, 'UDFZONE', f'ZONE {seq_name.split("-")[0]}')
    set_text(layout, 'UDFSEQUENCE', f'SEQUENCE {seq_name} OVERVIEW')
    set_text(layout, 'FIGURELABEL', seq_name)
    set_text(layout, 'TOTALFLUSHTIME', f"{int(round(totals['minutes']))} minutes")
    set_text(layout, 'TOTALFLUSHVOL', f"{int(round(totals['gallons'])):,} gallons")
    set_text(layout, 'TOTALVALVESOP', str(len(valves)))
    set_text(layout, 'TOTALHYDOP', str(len(hyds)))
    for text_name in ('PIPELENGTH', 'PIPEVOLUME', 'VOLUMETURNOVER', 'FLUSHDURATION', 'FLOWRATE', 'AVGVEL',
                      'PREHYDRANTPSI', 'BEGINRESHYDRANT', 'ENDRESHYDRANT', 'POSTHYDRANTPSI'):
        set_text(layout, text_name, ' ')
    for i in range(3):
        set_text(layout, f'HYDRANT{i + 1}', ' ')
    for i in range(6):
        set_text(layout, f'VALVECL{i + 1}', ' ')
        set_text(layout, f'VALVEOP{i + 1}', ' ')

    geoms = ([pipe_geom[p] for p in pipe_op if p in pipe_geom] + [hyd_geom[h] for h in hyds if h in hyd_geom]
             + [val_geom[v] for v in valves if v in val_geom])
    if geoms:
        minx, miny, maxx, maxy = extent_of(geoms, cfg['map_sr'])
        buf = cfg['buffer_dist']
        camera = frame.camera
        camera.setExtent(arcpy.Extent(minx - buf, miny - buf, maxx + buf, maxy + buf))
        if camera.scale < cfg['min_scale']:
            camera.scale = cfg['min_scale']
    # set after the extent so the legend only lists features visible in the frame
    setup_legend(layout, frame, keep, visible_only=True)
    if cfg['pdf_folder']:
        os.makedirs(cfg['pdf_folder'], exist_ok=True)
        layout.exportToPDF(os.path.join(cfg['pdf_folder'], f'{tag}.pdf'))
    return 1


# ---------------------------------------------------------------- main
def main():
    zip_path = get_param(0)
    if not zip_path:
        raise ValueError('A path to the flushing journal zip file is required')
    aprx = arcpy.mp.ArcGISProject('CURRENT')
    buffer_dist = float(get_param(1, 300.0))
    min_scale = float(get_param(2, 1000.0))
    pdf_folder = get_param(3)
    requested_sequences = [n.strip() for n in (get_param(4, '') or '').split(',') if n.strip()]
    symb_layers = find_symbology_layers(aprx)

    message(f'Reading {zip_path}')
    results, sequences, hydrants_gj, valves_gj, inp_text, meta, op_inps, zones_gj = load_zip(zip_path)
    if requested_sequences:
        wanted = {n.lower() for n in requested_sequences}
        selected_sequences = [s for s in sequences if str(s['name']).strip().lower() in wanted]
        missing = wanted - {str(s['name']).strip().lower() for s in selected_sequences}
        for name in requested_sequences:
            if name.lower() in missing:
                warn(f'Sequence {name} was not found in the project; skipped')
        if not selected_sequences:
            raise ValueError('None of the requested sequences were found in the project')
    else:
        selected_sequences = list(sequences)
    model_crs = str(meta.get('model_crs', 'EPSG:6625'))
    model_sr = arcpy.SpatialReference(int(model_crs.split(':')[-1]))
    geo_sr = arcpy.SpatialReference(4326)
    pipe_lines = pipe_geometry_table(inp_text)
    pipe_geom = {pid: arcpy.Polyline(arcpy.Array([arcpy.Point(x, y) for x, y in line]), model_sr)
                 for pid, line in pipe_lines.items()}

    layer_meta = meta.get('uploaded_layers') or {}
    hyd_field = (layer_meta.get('hydrants') or {}).get('id_field')
    val_field = (layer_meta.get('valves') or {}).get('id_field')
    hyd_map = build_mapping(meta, hydrants_gj, 'hydrants', hyd_field)  # GIS id -> junction
    intersections = intersection_nodes(inp_text, hyd_map.values())
    val_map = build_mapping(meta, valves_gj, 'valves', val_field)  # GIS id -> pipe

    hyd_geom = {}
    for f in hydrants_gj['features']:
        aid = feature_id(f.get('properties') or {}, hyd_field)
        if aid is None or not f.get('geometry'):
            continue
        x, y = f['geometry']['coordinates'][:2]
        hyd_geom[aid] = arcpy.PointGeometry(arcpy.Point(x, y), geo_sr)
    node_to_hyd = {}
    for gid, node in hyd_map.items():
        node_to_hyd.setdefault(node, gid)
    val_geom, val_label = {}, {}
    for f in valves_gj['features']:
        props = f.get('properties') or {}
        aid = feature_id(props, val_field)
        if aid is None or not f.get('geometry'):
            continue
        x, y = f['geometry']['coordinates'][:2]
        val_geom[aid] = arcpy.PointGeometry(arcpy.Point(x, y), geo_sr)
        val_label[aid] = str(props.get('VALVELABEL') or aid)

    all_labels = {f'{s["name"]}-{o["name"]}' for s in sequences for o in s.get('operations', [])}
    all_labels |= {overview_name(s['name']) for s in sequences}
    # the overview templates are never used as the operation map/layout template
    all_labels |= {OVERVIEW_MAP_TEMPLATE, OVERVIEW_LAYOUT_TEMPLATE}
    # skip maps/layouts generated by an earlier run so they are never used as the template
    template_map_obj = next((m for m in aprx.listMaps() if m.name not in all_labels), None)
    template_layout_obj = next((l for l in aprx.listLayouts() if l.name not in all_labels), None)
    if template_map_obj is None or template_layout_obj is None:
        raise ValueError('The project needs a template map and layout whose names are not operation names')
    template_map_name = template_map_obj.name
    template_layout_name = template_layout_obj.name
    overview_map_name = OVERVIEW_MAP_TEMPLATE
    if not any(m.name == overview_map_name for m in aprx.listMaps()):
        warn(f'Map {overview_map_name} not found; overview maps will be copied from {template_map_name}')
        overview_map_name = template_map_name
    overview_layout_name = OVERVIEW_LAYOUT_TEMPLATE
    if not any(l.name == overview_layout_name for l in aprx.listLayouts()):
        warn(f'Layout {overview_layout_name} not found; overview layouts will be copied from {template_layout_name}')
        overview_layout_name = template_layout_name
    map_sr = template_map_obj.spatialReference or model_sr
    gdb = aprx.defaultGeodatabase
    arcpy.env.overwriteOutput = True

    # base feature classes hold every pipe, hydrant and valve; each operation gets a copy with STATUS set
    pipes_base = new_fc(gdb, 'Pipes_Base', 'POLYLINE', model_sr, PIPE_FIELDS)
    with arcpy.da.InsertCursor(pipes_base, ['SHAPE@', 'EPANET_ID']) as cur:
        for pid, geom in pipe_geom.items():
            cur.insertRow([geom, pid])
    hyds_base = new_fc(gdb, 'Hydrants_Base', 'POINT', geo_sr, HYDRANT_FIELDS)
    with arcpy.da.InsertCursor(hyds_base, ['SHAPE@', 'ASSETID']) as cur:
        for hid, geom in hyd_geom.items():
            cur.insertRow([geom, hid])
    vals_base = new_fc(gdb, 'Valves_Base', 'POINT', geo_sr, VALVE_FIELDS)
    with arcpy.da.InsertCursor(vals_base, ['SHAPE@', 'ASSETID', 'FL_LABEL']) as cur:
        for vid, geom in val_geom.items():
            cur.insertRow([geom, vid, val_label[vid]])

    zones_fc = build_zones_fc(gdb, zones_gj, geo_sr) if zones_gj else None
    if zones_fc is None:
        warn('flushing_zones.geojson not found in the zip; overview maps will not show flushing zones')

    total = sum(len(s.get('operations', [])) for s in selected_sequences)
    arcpy.SetProgressor('step', 'Creating flushing maps', 0, total, 1)
    made = 0

    for seq in selected_sequences:
        seq_name = seq['name']
        seq_results = results.get(seq_name, {})
        flushed_pipes = set()
        flushed_hyds = {}  # hydrant GIS id -> label minutes
        seq_pipe_op, seq_op_order, seq_hyds, seq_valves, seq_notes = {}, [], [], {}, {}
        seq_totals = {'minutes': 0.0, 'gallons': 0.0}
        for op in seq['operations']:
            op_name = str(op['name'])
            close_v = [str(v).strip() for v in (op.get('close_valves') or []) if str(v).strip()]
            open_v = [str(v).strip() for v in (op.get('open_valves') or []) if str(v).strip()]
            # the app skips valves without a model mapping, closes first and then opens
            for v in close_v + open_v:
                if v not in val_map:
                    warn(f'{seq_name}-{op_name}: valve {v} is not mapped to a model pipe; ignored')
            close_v = [v for v in close_v if v in val_map]
            open_v = [v for v in open_v if v in val_map]
            res = seq_results.get(op_name) or {}
            open_h = [str(h).strip() for h in (op.get('open_hydrants') or []) if str(h).strip() in hyd_map]
            label = f'{seq_name}-{op_name}'
            tag = safe_name(label)
            map_name = label
            message(f'Building map {label}')

            pipes = res.get('flushed_pipes', [])
            vels = res.get('flushed_pipe_velocity_fps', [])
            lengths = res.get('pipe_length_ft', [])
            volumes = res.get('pipe_volume_gal', [])
            turnovers = float(res.get('options', {}).get('volume_turnovers', 3.0))
            hyd_ids = list(open_h)
            hyd_nodes = [hyd_map[h] for h in hyd_ids] or list(res.get('hydrant_nodes', []))
            if not hyd_ids:
                hyd_ids = [node_to_hyd.get(n, n) for n in hyd_nodes]
            minutes = str(int(res.get('total_flush_time_min', 0)) + 1) if pipes else ' '

            pipe_status, hyd_status, val_status = {}, {}, {}
            for pid in flushed_pipes:
                pipe_status[pid] = ('Flushed', ' ')
            for pid, vel in zip(pipes, vels):
                pipe_status[pid] = ('Current Sequence', str(round(vel, 1)))
            for pid in pipe_status:
                if pid not in pipe_geom:
                    warn(f'{label}: pipe {pid} has no geometry in {BASE_INP}')
            for hid, mins in flushed_hyds.items():
                hyd_status[hid] = ('Flushed', mins)
            for hid in hyd_ids:
                hyd_status[hid] = ('Current Sequence Open', minutes)
                if hid not in hyd_geom:
                    warn(f'{label}: hydrant {hid} not found in hydrants.geojson')
            for vid in close_v:
                val_status[vid] = 'Close'
            for vid in open_v:
                val_status[vid] = 'Reopen'
            val_note = {}
            for vid, status in val_status.items():
                if vid not in val_geom:
                    warn(f'{label}: valve {vid} not found in valves.geojson')
                    continue
                note = valve_leg_note(val_geom[vid], model_sr, intersections)
                if note:
                    val_note[vid] = note

            first_hyd = hyd_nodes[0] if hyd_nodes else ' '
            pipes_fc = copy_with_status(
                pipes_base, os.path.join(gdb, f'Pipes_{tag}'),
                ['EPANET_ID', 'STATUS', 'SEQUENCE', 'VELOCITY', 'HYDRANTID'],
                lambda r: ([r[0], pipe_status[r[0]][0], label, pipe_status[r[0]][1],
                            first_hyd if pipe_status[r[0]][0] == 'Current Sequence' else ' ']
                           if r[0] in pipe_status else None))
            hyd_fc = copy_with_status(
                hyds_base, os.path.join(gdb, f'Hydrants_{tag}'),
                ['ASSETID', HYD_STATUS_FLD, HYD_MIN_FLD],
                lambda r: [r[0], hyd_status[r[0]][0], hyd_status[r[0]][1]] if r[0] in hyd_status else None)
            val_fc = copy_with_status(
                vals_base, os.path.join(gdb, f'Valves_{tag}'),
                ['ASSETID', 'STATUS', 'NOTE'],
                lambda r: [r[0], val_status[r[0]], val_note.get(r[0])] if r[0] in val_status else None)
            active_geoms = ([pipe_geom[p] for p, s in pipe_status.items() if s[0] == 'Current Sequence' and p in pipe_geom]
                            + [hyd_geom[h] for h in hyd_ids if h in hyd_geom]
                            + [val_geom[v] for v in val_status if v in val_geom])

            delete_existing(aprx, map_name)
            seq_map = copy_item(aprx, 'map', template_map_name, map_name)
            valve_layer = seq_map.addDataFromPath(val_fc)
            hyd_layer = seq_map.addDataFromPath(hyd_fc)
            pipe_layer = seq_map.addDataFromPath(pipes_fc)
            for lyr, key, fc in ((valve_layer, 'valves', val_fc), (hyd_layer, 'hydrants', hyd_fc),
                                 (pipe_layer, 'pipes', pipes_fc)):
                count = int(arcpy.management.GetCount(fc)[0])
                message(f'  {key}: {count} features')
                lyr.visible = True
                apply_symbology(lyr, symb_layers.get(key), key)
            # drop the symbology source layers copied along with the template map
            for lyr in seq_map.listLayers():
                if lyr.name in SYMBOLOGY.values():
                    seq_map.removeLayer(lyr)
            label_valves(valve_layer)
            label_hydrants(hyd_layer)
            pipe_layer.showLabels = False

            layout = copy_item(aprx, 'layout', template_layout_name, map_name)
            frame = layout.listElements('MAPFRAME_ELEMENT')[0]
            frame.map = seq_map
            setup_legend(layout, frame, [valve_layer, hyd_layer, pipe_layer])
            camera = frame.camera

            geoms = active_geoms
            if geoms:
                minx, miny, maxx, maxy = extent_of(geoms, map_sr)
                camera.setExtent(arcpy.Extent(minx - buffer_dist, miny - buffer_dist,
                                              maxx + buffer_dist, maxy + buffer_dist))
                if camera.scale < min_scale:
                    camera.scale = min_scale

            # statistics for the layout text
            seconds = sum(l / v for l, v in zip(lengths, vels) if v > 0)
            gallons = sum(volumes)
            length = res.get('total_flush_length_ft') or sum(lengths)
            volume = res.get('total_flush_volume_gal') or gallons * turnovers
            flow = int(gallons / seconds * 60) if seconds > 0 else 0
            avg_vel = round(sum(lengths) / seconds, 1) if seconds > 0 else ' '
            orifice = (op.get('options') or {}).get('default_orifice_diam') or op.get('orifice_size') \
                or res.get('options', {}).get('default_orifice_diam', '')

            set_text(layout, 'UDFZONE', f'ZONE {seq_name.split("-")[0]}')
            set_text(layout, 'UDFSEQUENCE', f'SEQUENCE {op_name}')
            set_text(layout, 'FIGURELABEL', label)
            set_text(layout, 'PIPELENGTH', str(int(length)) if length > 0 else ' ')
            set_text(layout, 'PIPEVOLUME', str(int(volume)) if volume > 0 else ' ')
            set_text(layout, 'VOLUMETURNOVER', str(turnovers) if volume > 0 else ' ')
            set_text(layout, 'FLUSHDURATION', minutes)
            set_text(layout, 'FLOWRATE', str(flow) if flow > 0 else ' ')
            set_text(layout, 'AVGVEL', str(avg_vel))
            for name in ('PREHYDRANTPSI', 'BEGINRESHYDRANT', 'ENDRESHYDRANT', 'POSTHYDRANTPSI'):
                set_text(layout, name, ' ')  # pressures are not recorded in the results dictionary
            for i in range(3):
                if i < len(hyd_ids):
                    size = orifice if i == 0 and orifice else ''
                    set_text(layout, f'HYDRANT{i + 1}', f'{hyd_ids[i]} ({size} in)' if size else hyd_ids[i])
                else:
                    set_text(layout, f'HYDRANT{i + 1}', ' ')
            def valve_text(vid):
                text = val_label.get(vid, vid)
                return f'{text} {val_note[vid]}' if vid in val_note else text

            for i in range(6):
                set_text(layout, f'VALVECL{i + 1}', valve_text(close_v[i]) if i < len(close_v) else ' ')
                set_text(layout, f'VALVEOP{i + 1}', valve_text(open_v[i]) if i < len(open_v) else ' ')

            if pdf_folder:
                os.makedirs(pdf_folder, exist_ok=True)
                layout.exportToPDF(os.path.join(pdf_folder, f'{tag}.pdf'))

            flushed_pipes.update(pipes)
            seq_totals['minutes'] += float(res.get('total_flush_time_min') or 0)
            seq_totals['gallons'] += float(res.get('total_flush_volume_gal') or 0)
            for hid in hyd_ids:
                flushed_hyds[hid] = f'{op_name}|{minutes}'
                if hid not in seq_hyds:
                    seq_hyds.append(hid)
            if pipes:
                seq_op_order.append(op_name)
            for pid in pipes:
                seq_pipe_op.setdefault(pid, op_name)
            for vid, status in val_status.items():
                if seq_valves.get(vid) != 'Close':  # a valve that was closed stays shown as closed
                    seq_valves[vid] = status
                if vid in val_note:
                    seq_notes[vid] = val_note[vid]
            made += 1
            arcpy.SetProgressorPosition()

        if seq['operations']:
            message(f'Building overview map for {seq_name}')
            made += build_overview(
                aprx, seq_name, seq_pipe_op, seq_op_order, seq_hyds, seq_valves, seq_notes,
                dict(pipes_base=pipes_base, hyds_base=hyds_base, vals_base=vals_base, zones_fc=zones_fc),
                dict(gdb=gdb, symb_layers=symb_layers, overview_map_name=overview_map_name,
                     overview_layout_name=overview_layout_name, map_sr=map_sr,
                     buffer_dist=buffer_dist, min_scale=min_scale, pdf_folder=pdf_folder),
                pipe_geom, hyd_geom, val_geom, seq_totals)

    aprx.save()
    message(f'Created {made} flushing maps and layouts')


if __name__ == '__main__':
    main()
