let map;
let modelPipeLayer;
let uploadedLayerGroups = { valves: null, hydrants: null };
let pendingModelFile = null;
let modelLoaded = false;
let hydrantsLoaded = false;

document.addEventListener("DOMContentLoaded", function () {
    initializeTabs();
    initializeSidebarModeButtons();
    initializeMap();
    initializeToolbar();
    initializeModelUpload();
    initializeLayerUpload();
    initializePdfDownload();
});

function initializeTabs() {
    const tabButtons = document.querySelectorAll(".tab-button");

    tabButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            tabButtons.forEach(function (btn) {
                btn.classList.remove("active");
            });

            button.classList.add("active");
        });
    });
}

async function persistMovedFeature(layerType, marker) {
    if (!marker) return;

    const feature = marker.feature || null;
    if (!feature) {
        // nothing to persist
        return;
    }

    // try to determine id field and id value
    const idSelect = document.getElementById(`${layerType}IdFieldSelect`);
    const idField = idSelect && idSelect.value ? idSelect.value : null;
    const props = feature.properties || {};
    const idValue = idField ? props[idField] : (props.id || props.ID || props.name || null);

    const payload = {
        layer_type: layerType,
        id_field: idField,
        id_value: idValue,
        feature: feature
    };

    const statusDiv = document.getElementById(layerType + 'UploadStatus');
    if (statusDiv) {
        statusDiv.textContent = 'Saving moved feature...';
        statusDiv.classList.remove('error');
    }

    try {
        const response = await fetch('/update_feature_geometry', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || 'Failed to save moved feature.');
        }

        if (statusDiv) {
            statusDiv.textContent = data.message || 'Moved feature saved.';
        }
    } catch (err) {
        console.error(err);
        if (statusDiv) {
            statusDiv.textContent = err.message || 'Error saving moved feature.';
            statusDiv.classList.add('error');
        }
    }
}

function initializeSidebarModeButtons() {
    const modeButtons = document.querySelectorAll(".sidebar-mode-button");

    modeButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            modeButtons.forEach(function (btn) {
                btn.classList.remove("active");
            });

            button.classList.add("active");
            setActiveSidebarToolbar(button.getAttribute("data-toolbar-target"));
            updateAllLayersDraggability();
        });
    });

    // Initialize to the existing active button or default to project
    const initial = document.querySelector('.sidebar-mode-button.active') || document.querySelector('.sidebar-mode-button[data-toolbar-target="project"]');
    if (initial) {
        setActiveSidebarToolbar(initial.getAttribute('data-toolbar-target'));
    } else {
        setActiveSidebarToolbar('project');
    }
    updateAllLayersDraggability();
}

function updateAllLayersDraggability() {
    const active = document.querySelector('.sidebar-mode-button.active')?.getAttribute('data-toolbar-target') || 'project';

    // Hydrants should be draggable only when hydrants toolbar is active
    enableLayerDraggability('hydrants', active === 'hydrants');

    // Valves should be draggable only when valves toolbar is active
    enableLayerDraggability('valves', active === 'valves');
}

function enableLayerDraggability(layerType, enabled) {
    const group = uploadedLayerGroups[layerType];

    if (!group) return;

    group.eachLayer(function (layer) {
        if (layer instanceof L.Marker) {
            if (enabled) {
                if (layer.dragging) {
                    layer.dragging.enable();
                } else {
                    layer.options.draggable = true;
                }
                // attach dragend handler
                layer.off('dragend');
                layer.on('dragend', function (e) {
                    const p = e.target.getLatLng();
                    const statusDiv = document.getElementById(layerType + 'UploadStatus');
                    if (statusDiv) statusDiv.textContent = `Moved ${layerType.slice(0, -1)} to ${p.lat.toFixed(6)}, ${p.lng.toFixed(6)}`;
                    if (layer.feature && layer.feature.geometry) {
                        layer.feature.geometry.coordinates = [p.lng, p.lat];
                    }
                    persistMovedFeature(layerType, layer);
                });
            } else {
                if (layer.dragging) {
                    layer.dragging.disable();
                } else {
                    layer.options.draggable = false;
                }
                layer.off('dragend');
            }
        }
    });
}

function setActiveSidebarToolbar(toolbarName) {
    const toolbarSections = document.querySelectorAll(".toolbar-section");
    const title = document.querySelector(".toolbar-title");

    toolbarSections.forEach(function (section) {
        const isActive = section.getAttribute("data-toolbar") === toolbarName;
        section.classList.toggle("hidden", !isActive);
    });

    if (title) {
        title.textContent = toolbarName.charAt(0).toUpperCase() + toolbarName.slice(1);
    }
}

function initializeToolbar() {
    const toolButtons = document.querySelectorAll(".tool-button");

    toolButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            toolButtons.forEach(function (btn) {
                btn.classList.remove("active");
            });

            button.classList.add("active");
        });
    });

    const zoomToProjectBtn = document.getElementById("zoomToProjectBtn");
    const connectHydrantsBtn = document.getElementById("connectHydrantsBtn");
    const downloadProjectBtn = document.getElementById("downloadProjectBtn");
    const uploadProjectBtn = document.getElementById("uploadProjectBtn");

    if (zoomToProjectBtn) {
        zoomToProjectBtn.addEventListener("click", zoomToProject);
    }

    if (connectHydrantsBtn) {
        connectHydrantsBtn.disabled = true;
        connectHydrantsBtn.addEventListener("click", connectHydrantsToModel);
    }

    if (downloadProjectBtn) {
        downloadProjectBtn.addEventListener("click", downloadProjectZip);
    }

    if (uploadProjectBtn) {
        uploadProjectBtn.addEventListener("click", uploadProjectZip);
    }
}

function updateConnectHydrantsButtonState() {
    const connectHydrantsBtn = document.getElementById("connectHydrantsBtn");

    if (!connectHydrantsBtn) {
        return;
    }

    connectHydrantsBtn.disabled = !(modelLoaded && hydrantsLoaded);
}

function initializeMap() {
    const initialCenter = [40.130, -111.580];

    map = L.map("map", {
        zoomControl: true,
        attributionControl: false,
        preferCanvas: true
    }).setView(initialCenter, 16);

    L.tileLayer(
        "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        {
            maxZoom: 26,
            maxNativeZoom: 19,
            crossOrigin: true
        }
    ).addTo(map);

    modelPipeLayer = L.geoJSON(null, {
        style: styleModelPipe,
        onEachFeature: onEachModelPipe
    }).addTo(map);

    uploadedLayerGroups = {
        valves: L.layerGroup().addTo(map),
        hydrants: L.layerGroup().addTo(map)
    };

    setTimeout(function () {
        map.invalidateSize();
    }, 250);

    // Ensure marker draggability is in sync after layers are created
    updateAllLayersDraggability();
}

function initializeModelUpload() {
    const loadModelBtn = document.getElementById("loadModelBtn");
    const modal = document.getElementById("epsgModal");
    const closeBtn = document.getElementById("closeEpsgModal");
    const cancelBtn = document.getElementById("cancelEpsgModal");
    const confirmBtn = document.getElementById("confirmEpsgModal");
    const epsgInput = document.getElementById("epsgInput");
    const epsgError = document.getElementById("epsgModalError");

    if (!loadModelBtn || !modal || !closeBtn || !cancelBtn || !confirmBtn || !epsgInput || !epsgError) {
        return;
    }

    loadModelBtn.addEventListener("click", async function () {
        await selectModelFile();
    });

    closeBtn.addEventListener("click", hideEpsgModal);
    cancelBtn.addEventListener("click", hideEpsgModal);

    modal.addEventListener("click", function (event) {
        if (event.target === modal) {
            hideEpsgModal();
        }
    });

    document.addEventListener("keydown", function (event) {
        if (event.key === "Escape" && !modal.classList.contains("hidden")) {
            hideEpsgModal();
        }
    });

    confirmBtn.addEventListener("click", function () {
        const epsgValue = epsgInput.value.trim();

        if (!epsgValue) {
            epsgError.textContent = "EPSG code is required.";
            return;
        }

        const modelCrs = epsgValue.toUpperCase().startsWith("EPSG:")
            ? epsgValue
            : `EPSG:${epsgValue}`;

        hideEpsgModal();
        submitModelFile(pendingModelFile, modelCrs);
    });
}

function initializeLayerUpload() {
    const layerButtons = document.querySelectorAll("[data-upload-layer]");
    const valvesIdFieldSelect = document.getElementById("valvesIdFieldSelect");
    const hydrantsIdFieldSelect = document.getElementById("hydrantsIdFieldSelect");

    layerButtons.forEach(function (button) {
        button.addEventListener("click", function () {
            uploadPointShapefile(button.getAttribute("data-upload-layer"));
        });
    });

    if (valvesIdFieldSelect) {
        valvesIdFieldSelect.addEventListener("change", function () {
            setLayerIdField("valves", valvesIdFieldSelect.value);
        });
    }

    if (hydrantsIdFieldSelect) {
        hydrantsIdFieldSelect.addEventListener("change", function () {
            setLayerIdField("hydrants", hydrantsIdFieldSelect.value);
        });
    }
}

async function downloadProjectZip() {
    const projectStatus = document.getElementById("projectLoadStatus");
    if (projectStatus) {
        projectStatus.textContent = "Exporting project...";
        projectStatus.classList.remove("error");
    }

    try {
        const response = await fetch("/download_project", {
            method: "GET"
        });

        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.message || "Failed to export project.");
        }

        const blob = await response.blob();
        const url = window.URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "flushing_journal_project.zip";
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        window.URL.revokeObjectURL(url);

        if (projectStatus) {
            projectStatus.textContent = "Project export ready.";
        }
    } catch (error) {
        console.error(error);
        if (projectStatus) {
            projectStatus.textContent = error.message;
            projectStatus.classList.add("error");
        }
    }
}

async function uploadProjectZip() {
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = ".zip";
    fileInput.style.display = "none";

    document.body.appendChild(fileInput);

    const file = await new Promise((resolve) => {
        fileInput.addEventListener("change", function () {
            resolve(fileInput.files[0]);
        }, { once: true });

        fileInput.click();
    });

    document.body.removeChild(fileInput);

    const projectStatus = document.getElementById("projectLoadStatus");
    if (!file) {
        if (projectStatus) {
            projectStatus.textContent = "No project file selected.";
            projectStatus.classList.add("error");
        }
        return;
    }

    const formData = new FormData();
    formData.append("project_zip", file);

    if (projectStatus) {
        projectStatus.textContent = "Importing project...";
        projectStatus.classList.remove("error");
    }

    try {
        const response = await fetch("/upload_project", {
            method: "POST",
            body: formData
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || "Failed to import project.");
        }

        if (data.pipe_geojson) {
            displayModelPipes(data.pipe_geojson);
            modelLoaded = true;
        }

        if (data.hydrants) {
            displayPointLayer("hydrants", data.hydrants.geojson);
            populateLayerFieldSelect("hydrants", data.hydrants.fields || [], data.hydrants.selected_id_field || "");
            hydrantsLoaded = true;
        } else {
            hydrantsLoaded = false;
        }

        if (data.valves) {
            displayPointLayer("valves", data.valves.geojson);
            populateLayerFieldSelect("valves", data.valves.fields || [], data.valves.selected_id_field || "");
        }

        updateConnectHydrantsButtonState();

        if (projectStatus) {
            projectStatus.textContent = data.message || "Project loaded successfully.";
        }
    } catch (error) {
        console.error(error);
        if (projectStatus) {
            projectStatus.textContent = error.message;
            projectStatus.classList.add("error");
        }
    }
}

async function uploadPointShapefile(layerType) {
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = ".shp,.shx,.dbf,.prj";
    fileInput.multiple = true;
    fileInput.style.display = "none";

    document.body.appendChild(fileInput);

    const files = await new Promise((resolve) => {
        fileInput.addEventListener("change", function () {
            resolve(Array.from(fileInput.files || []));
        }, { once: true });

        fileInput.click();
    });

    document.body.removeChild(fileInput);

    if (!files.length) {
        setLayerStatus(layerType, "No files selected.", true);
        return;
    }

    const formData = new FormData();

    files.forEach(function (file) {
        formData.append("shape_files", file);
    });

    formData.append("layer_type", layerType);

    setLayerStatus(layerType, "Uploading shapefile...", false);

    try {
        const response = await fetch("/upload_shapefile", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || "Shapefile upload failed.");
        }

        displayPointLayer(layerType, data.geojson);
        setLayerStatus(layerType, `Loaded ${data.feature_count} ${layerType} features.`, false);
        populateLayerFieldSelect(layerType, data.field_names || [], data.selected_id_field || "");

        if (layerType === "hydrants") {
            hydrantsLoaded = true;
            updateConnectHydrantsButtonState();
        }
    } catch (error) {
        console.error(error);
        setLayerStatus(layerType, error.message, true);

        if (layerType === "hydrants") {
            hydrantsLoaded = false;
            updateConnectHydrantsButtonState();
        }
    }
}

function populateLayerFieldSelect(layerType, fieldNames, selectedField) {
    const select = document.getElementById(`${layerType}IdFieldSelect`);
    const container = document.getElementById(`${layerType}FieldSelector`);

    if (!select || !container) {
        return;
    }

    select.innerHTML = "";

    if (!fieldNames || !fieldNames.length) {
        container.style.display = "none";
        return;
    }

    const placeholder = document.createElement("option");
    placeholder.value = "";
    placeholder.textContent = "Select ID field";
    placeholder.disabled = true;
    placeholder.selected = !selectedField;
    select.appendChild(placeholder);

    fieldNames.forEach(function (fieldName) {
        const option = document.createElement("option");
        option.value = fieldName;
        option.textContent = fieldName;
        select.appendChild(option);
    });

    if (selectedField && fieldNames.includes(selectedField)) {
        select.value = selectedField;
    }

    container.style.display = "block";
}

async function setLayerIdField(layerType, idField) {
    if (!layerType || !idField) {
        return;
    }

    try {
        const response = await fetch("/set_layer_id_field", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            },
            body: JSON.stringify({
                layer_type: layerType,
                id_field: idField
            })
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || "Failed to save layer ID field.");
        }

        setLayerStatus(layerType, `ID field set to ${data.selected_id_field}.`, false);
    } catch (error) {
        console.error(error);
        setLayerStatus(layerType, error.message, true);
    }
}

async function selectModelFile() {
    const fileInput = document.createElement("input");
    fileInput.type = "file";
    fileInput.accept = ".inp";
    fileInput.style.display = "none";

    document.body.appendChild(fileInput);

    const file = await new Promise((resolve) => {
        fileInput.addEventListener("change", function () {
            resolve(fileInput.files[0]);
        }, { once: true });

        fileInput.click();
    });

    document.body.removeChild(fileInput);

    if (!file) {
        setModelStatus("No file selected.", true);
        return;
    }

    showEpsgModal(file);
}

function showEpsgModal(file) {
    pendingModelFile = file;

    const modal = document.getElementById("epsgModal");
    const epsgInput = document.getElementById("epsgInput");
    const epsgError = document.getElementById("epsgModalError");

    if (!modal || !epsgInput || !epsgError) {
        return;
    }

    epsgError.textContent = "";
    epsgInput.value = "26912";
    modal.classList.remove("hidden");

    setTimeout(function () {
        epsgInput.focus();
        epsgInput.select();
    }, 50);
}

function hideEpsgModal() {
    const modal = document.getElementById("epsgModal");
    const epsgInput = document.getElementById("epsgInput");
    const epsgError = document.getElementById("epsgModalError");

    if (!modal || !epsgInput || !epsgError) {
        return;
    }

    modal.classList.add("hidden");
    epsgInput.value = "6625";
    epsgError.textContent = "";
}

async function submitModelFile(file, modelCrs) {
    if (!file) {
        setModelStatus("No file selected.", true);
        return;
    }

    const loadModelBtn = document.getElementById("loadModelBtn");
    const formData = new FormData();

    formData.append("inp_file", file);
    formData.append("model_crs", modelCrs);

    if (loadModelBtn) {
        loadModelBtn.disabled = true;
    }

    setModelStatus("Loading model...", false);

    try {
        const response = await fetch("/upload_model", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || "Model upload failed.");
        }

        displayModelPipes(data.pipe_geojson);
        setModelStatus(`Loaded ${data.pipe_count} pipes from model.`, false);
        modelLoaded = true;
        updateConnectHydrantsButtonState();
    } catch (error) {
        console.error(error);
        setModelStatus(error.message, true);
        modelLoaded = false;
        updateConnectHydrantsButtonState();
    } finally {
        if (loadModelBtn) {
            loadModelBtn.disabled = false;
        }

        pendingModelFile = null;
    }
}

function displayModelPipes(pipeGeojson) {
    if (!modelPipeLayer) {
        modelPipeLayer = L.geoJSON(null, {
            style: styleModelPipe,
            onEachFeature: onEachModelPipe
        }).addTo(map);
    }

    modelPipeLayer.clearLayers();
    modelPipeLayer.addData(pipeGeojson);

    const bounds = modelPipeLayer.getBounds();

    if (bounds.isValid()) {
        map.fitBounds(bounds, {
            padding: [20, 20]
        });
    }

    setTimeout(function () {
        map.invalidateSize();
    }, 100);
}

function styleModelPipe(feature) {
    return {
        color: "#222222",
        weight: 3,
        opacity: 1.0
    };
}

function onEachModelPipe(feature, layer) {
    const props = feature.properties || {};

    const popupHtml = `
        <strong>${props.name || props.id || "Pipe"}</strong><br>
        Start Node: ${props.start_node || ""}<br>
        End Node: ${props.end_node || ""}<br>
        Length: ${formatPopupNumber(props.length)}<br>
        Diameter: ${formatPopupNumber(props.diameter)}
    `;

    layer.bindPopup(popupHtml);
}

function formatPopupNumber(value) {
    if (value === null || value === undefined || value === "") {
        return "";
    }

    const numberValue = Number(value);

    if (Number.isNaN(numberValue)) {
        return value;
    }

    return numberValue.toLocaleString(undefined, {
        maximumFractionDigits: 3
    });
}

function setModelStatus(message, isError) {
    const statusDiv = document.getElementById("modelLoadStatus");

    if (!statusDiv) {
        return;
    }

    statusDiv.textContent = message;
    statusDiv.classList.toggle("error", Boolean(isError));
}

function setLayerStatus(layerType, message, isError) {
    const statusDiv = document.getElementById(`${layerType}UploadStatus`);

    if (!statusDiv) {
        return;
    }

    statusDiv.textContent = message;
    statusDiv.classList.toggle("error", Boolean(isError));
}

function displayPointLayer(layerType, geojson) {
    const layerGroup = uploadedLayerGroups[layerType];

    if (!layerGroup) {
        return;
    }

    layerGroup.clearLayers();

    if (!geojson || !geojson.features || !geojson.features.length) {
        return;
    }

    const pointLayer = L.geoJSON(geojson, {
        pointToLayer: function (feature, latlng) {
            const props = feature.properties || {};
            const label = props.name || props.id || layerType;

            if (layerType === "valves") {
                return addValveMarker(latlng, label, props.status || "untouched", layerGroup, 'valves', feature);
            }

            return addHydrantMarker(latlng, label, props.status || "untouched", layerGroup, 'hydrants', feature);
        }
    });

    pointLayer.addTo(layerGroup);

    setTimeout(function () {
        map.invalidateSize();
    }, 100);
}

function addValveMarker(latlng, label, status, targetLayer, layerType, feature) {
    let color = "#d4ff00";

    if (status === "reopen") {
        color = "#0066ff";
    } else if (status === "close") {
        color = "#e00000";
    }

    const icon = L.divIcon({
        className: "",
        html: `<div class="map-valve-marker" style="background:${color};"></div>`,
        iconSize: [9, 9],
        iconAnchor: [9, 9]
    });

    const active = document.querySelector('.sidebar-mode-button.active')?.getAttribute('data-toolbar-target') || 'project';
    const draggable = active === (layerType || 'valves');

    const marker = L.marker(latlng, {
        icon: icon,
        draggable: !!draggable
    }).addTo(targetLayer || map);

    // attach the original feature so we can persist updates
    if (feature) {
        marker.feature = feature;
    }

    if (draggable) {
        marker.on('dragend', function (e) {
            const p = e.target.getLatLng();
            const statusDiv = document.getElementById('valvesUploadStatus');
            if (statusDiv) statusDiv.textContent = `Moved valve to ${p.lat.toFixed(6)}, ${p.lng.toFixed(6)}`;
            // update in-memory feature geometry and persist
            if (marker.feature && marker.feature.geometry) {
                marker.feature.geometry.coordinates = [p.lng, p.lat];
            }
            persistMovedFeature('valves', marker);
        });
    } else {
        // ensure no dragging handlers are active
        marker.off('dragend');
    }

    return marker;
}

function addHydrantMarker(latlng, label, status, targetLayer, layerType, feature) {
    let color = "#ff0000";

    if (status === "flushed") {
        color = "#0047ff";
    } else if (status === "current") {
        color = "#00aa44";
    }

    const icon = L.divIcon({
        className: "",
        html: `<div class="map-hydrant-marker" style="background:${color};"></div>`,
        iconSize: [16, 16],
        iconAnchor: [8, 8]
    });

    const active = document.querySelector('.sidebar-mode-button.active')?.getAttribute('data-toolbar-target') || 'project';
    const draggable = active === (layerType || 'hydrants');

    const marker = L.marker(latlng, {
        icon: icon,
        draggable: !!draggable
    }).addTo(targetLayer || map).bindPopup(label);

    if (feature) {
        marker.feature = feature;
    }

    if (draggable) {
        marker.on('dragend', function (e) {
            const p = e.target.getLatLng();
            const statusDiv = document.getElementById('hydrantsUploadStatus');
            if (statusDiv) statusDiv.textContent = `Moved hydrant to ${p.lat.toFixed(6)}, ${p.lng.toFixed(6)}`;
            if (marker.feature && marker.feature.geometry) {
                marker.feature.geometry.coordinates = [p.lng, p.lat];
            }
            persistMovedFeature('hydrants', marker);
        });
    } else {
        marker.off('dragend');
    }

    return marker;
}

async function connectHydrantsToModel() {
    const connectHydrantsBtn = document.getElementById("connectHydrantsBtn");
    const hydrantsConnectStatus = document.getElementById("hydrantsConnectStatus");

    if (!connectHydrantsBtn) {
        return;
    }

    connectHydrantsBtn.disabled = true;
    hydrantsConnectStatus.textContent = "Connecting hydrants to model...";
    hydrantsConnectStatus.classList.remove("error");

    try {
        const response = await fetch("/connect_hydrants", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            }
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
            throw new Error(data.message || "Failed to connect hydrants.");
        }

        displayModelPipes(data.pipe_geojson);
        hydrantsConnectStatus.textContent = data.message || "Hydrants connected successfully.";
        modelLoaded = true;
        updateConnectHydrantsButtonState();
    } catch (error) {
        console.error(error);
        hydrantsConnectStatus.textContent = error.message;
        hydrantsConnectStatus.classList.add("error");
        connectHydrantsBtn.disabled = false;
    }
}

function zoomToProject() {
    if (!map) {
        return;
    }

    if (modelPipeLayer && modelPipeLayer.getBounds().isValid()) {
        map.fitBounds(modelPipeLayer.getBounds(), {
            padding: [20, 20]
        });
        return;
    }

    const bounds = L.latLngBounds([
        [40.12970, -111.58700],
        [40.13110, -111.57580]
    ]);

    map.fitBounds(bounds, {
        padding: [20, 20]
    });
}

function initializePdfDownload() {
    const downloadPdfBtn = document.getElementById("downloadPdfBtn");

    if (!downloadPdfBtn) {
        return;
    }

    downloadPdfBtn.addEventListener("click", async function () {
        await downloadJournalAsPdf();
    });
}

async function downloadJournalAsPdf() {
    const sheet = document.getElementById("journalSheet");

    if (map) {
        map.invalidateSize();
    }

    sheet.classList.add("exporting");

    const originalScrollX = window.scrollX;
    const originalScrollY = window.scrollY;

    window.scrollTo(0, 0);

    const options = {
        margin: 0,
        filename: "Flushing_Journal_11x17.pdf",
        image: {
            type: "jpeg",
            quality: 0.98
        },
        html2canvas: {
            scale: 2,
            useCORS: true,
            allowTaint: true,
            backgroundColor: "#ffffff",
            logging: false,
            width: sheet.offsetWidth,
            height: sheet.offsetHeight,
            windowWidth: sheet.scrollWidth,
            windowHeight: sheet.scrollHeight
        },
        jsPDF: {
            unit: "in",
            format: [17, 11],
            orientation: "landscape",
            compress: true
        },
        pagebreak: {
            mode: ["avoid-all"]
        }
    };

    try {
        await html2pdf().set(options).from(sheet).save();
    } finally {
        sheet.classList.remove("exporting");
        window.scrollTo(originalScrollX, originalScrollY);
    }
}