let map;
let modelPipeLayer;
let uploadedLayerGroups = { valves: null, hydrants: null };
let pendingModelFile = null;
let modelLoaded = false;
let hydrantsLoaded = false;
let valvesLoaded = false;
let selectedValveMarker = null;
let originalValveLocationMarker = null;

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

    if (toolbarName !== 'valves') {
        clearSelectedValveMarker();
    } else if (selectedValveMarker) {
        renderSelectedValveOriginalLocation(selectedValveMarker);
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

    const snapValvesBtn = document.getElementById("snapValvesBtn");
    if (snapValvesBtn) {
        snapValvesBtn.disabled = true;
        snapValvesBtn.addEventListener("click", snapAllValvesToPipes);
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

function updateSnapValvesButtonState() {
    const snapValvesBtn = document.getElementById("snapValvesBtn");

    if (!snapValvesBtn) {
        return;
    }

    snapValvesBtn.disabled = !(modelLoaded && valvesLoaded);
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

    const sequenceTabContainer = document.getElementById("sequenceTabs");
    const sequencePanelContainer = document.getElementById("sequencePanels");
    if (sequenceTabContainer) {
        sequenceTabContainer.addEventListener("click", function (event) {
            const button = event.target.closest(".sequence-tab-button");
            if (!button) {
                return;
            }
            selectSequenceTab(button.dataset.sequenceName);
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
            valvesLoaded = true;
            updateSnapValvesButtonState();
        }

        updateConnectHydrantsButtonState();

        if (data.sequences) {
            renderSequences(data.sequences, data.message || "Project loaded successfully.");
        }

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
    fileInput.accept = layerType === "sequences" ? ".txt" : ".shp,.shx,.dbf,.prj";
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

    if (layerType === "sequences") {
        return uploadSequenceFiles(files);
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

        if (layerType === "valves") {
            valvesLoaded = true;
            updateSnapValvesButtonState();
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

function setSequenceStatus(message, isError) {
    const statusDiv = document.getElementById("sequenceLoaderStatus");

    if (!statusDiv) {
        return;
    }

    statusDiv.textContent = message;
    statusDiv.classList.toggle("error", Boolean(isError));
}

async function uploadSequenceFiles(files) {
    const sequenceTabs = document.getElementById("sequenceTabs");
    const sequencePanels = document.getElementById("sequencePanels");

    if (!sequenceTabs || !sequencePanels) {
        setSequenceStatus("Sequence UI is not available.", true);
        return;
    }

    const formData = new FormData();
    files.forEach(function (file) {
        formData.append("sequence_files", file);
    });

    try {
        setSequenceStatus(`Loading ${files.length} sequence file(s)...`, false);

        const response = await fetch("/upload_sequences", {
            method: "POST",
            body: formData
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || "Failed to upload sequence files.");
        }

        renderSequences(data.sequences || [], data.message);
    } catch (error) {
        console.error(error);
        setSequenceStatus(error.message || "Failed to load sequences.", true);
    }
}

function renderSequences(sequences, message) {
    const sequenceTabs = document.getElementById("sequenceTabs");
    const sequencePanels = document.getElementById("sequencePanels");

    if (!sequenceTabs || !sequencePanels) {
        setSequenceStatus("Sequence UI is not available.", true);
        return;
    }

    sequenceTabs.innerHTML = "";
    sequencePanels.innerHTML = "";

    if (!Array.isArray(sequences) || sequences.length === 0) {
        setSequenceStatus(message || "No sequences loaded.", false);
        return;
    }

    sequences.forEach((sequence, index) => {
        const sequenceName = sequence.name || `Sequence ${index + 1}`;

        const tabButton = document.createElement("button");
        tabButton.type = "button";
        tabButton.className = "sequence-tab-button";
        tabButton.dataset.sequenceName = sequenceName;
        tabButton.textContent = sequenceName;
        if (index === 0) {
            tabButton.classList.add("active");
        }
        tabButton.addEventListener("click", function () {
            selectSequenceTab(sequenceName);
        });
        sequenceTabs.appendChild(tabButton);

        const panel = document.createElement("div");
        panel.className = `sequence-panel${index === 0 ? " active" : ""}`;
        panel.dataset.sequenceName = sequenceName;

        (sequence.operations || []).forEach((operation) => {
            const operationSection = document.createElement("div");
            operationSection.className = "sequence-operation";

            const operationHeader = document.createElement("button");
            operationHeader.type = "button";
            operationHeader.className = "sequence-operation-header";
            operationHeader.textContent = operation.name || "Operation";
            operationHeader.addEventListener("click", function () {
                operationSection.classList.toggle("open");
            });
            operationSection.appendChild(operationHeader);

            const operationContent = document.createElement("div");
            operationContent.className = "sequence-operation-content";

            operationContent.appendChild(createControlRow("Open Valves", (operation.open_valves || operation.openValves || []).join(","), "open-valves"));
            operationContent.appendChild(createControlRow("Close Valves", (operation.close_valves || operation.closeValves || []).join(","), "close-valves"));
            operationContent.appendChild(createControlRow("Open Hydrants", (operation.open_hydrants || operation.openHydrants || []).join(","), "open-hydrants"));

            operationContent.appendChild(createFloatInputRow(operation));
            operationContent.appendChild(createControlRow("Map Message", operation.map_message || operation.mapMessage || "", "map-message", false));

            operationSection.appendChild(operationContent);
            panel.appendChild(operationSection);
        });

        sequencePanels.appendChild(panel);
    });

    selectSequenceTab(sequences[0].name || `Sequence 1`);
    setSequenceStatus(message || `Loaded ${sequences.length} sequence${sequences.length === 1 ? "" : "s"}.`, false);
}

function parseSequenceFile(fileName, text) {
    const sequence = {
        name: fileName.replace(/\.txt$/i, ""),
        operations: []
    };

    const sequenceNameMatch = text.match(/\[([^\]]+)\]/);
    if (sequenceNameMatch) {
        sequence.name = sequenceNameMatch[1].trim();
    }

    const operationBlocks = text.split(/\r?\n(?=\(\d+\))/g).map((block) => block.trim()).filter(Boolean);

    operationBlocks.forEach((block) => {
        const operationMatch = block.match(/^\((\d+)\)/);
        if (!operationMatch) {
            return;
        }

        const operationName = `Operation ${operationMatch[1]}`;
        const openValves = [];
        const closeValves = [];
        const openHydrants = [];
        let orificeSize = "";
        let targetVelocity = "";
        let mapMessage = "";

        const openValvesMatch = block.match(/>([^<]*)</);
        if (openValvesMatch) {
            const values = openValvesMatch[1].trim();
            openValves.push(...parseCommaSeparatedTokens(values));
        }

        const closeValvesMatch = block.match(/<([^>]*)>/);
        if (closeValvesMatch) {
            const values = closeValvesMatch[1].trim();
            if (values) {
                closeValves.push(...parseCommaSeparatedTokens(values));
            }
        }

        const hydrantsMatch = block.match(/\{([^}]*)\}/);
        if (hydrantsMatch) {
            const values = hydrantsMatch[1].trim();
            if (values) {
                const parts = values.split("*").map((value) => value.trim());
                if (parts.length >= 1 && parts[0]) {
                    openHydrants.push(parts[0]);
                }
                if (parts.length >= 2 && parts[1]) {
                    orificeSize = parts[1];
                }
            }
        }

        const mapMessageMatch = block.match(/\|([^|]*)\|/);
        if (mapMessageMatch) {
            mapMessage = mapMessageMatch[1].trim();
        }

        const hasTargetVelocity = !orificeSize && openHydrants.length > 0 && block.includes("*");
        if (hasTargetVelocity) {
            targetVelocity = "";
        }

        sequence.operations.push({
            name: operationName,
            open_valves: openValves,
            close_valves: closeValves,
            open_hydrants: openHydrants,
            orifice_size: orificeSize,
            target_velocity: targetVelocity,
            toggle_mode: orificeSize ? "Orifice Size" : "Target Velocity",
            map_message: mapMessage
        });
    });

    return sequence;
}

function parseCommaSeparatedTokens(text) {
    if (!text) {
        return [];
    }

    return text.split(",").map((token) => token.trim()).filter(Boolean);
}

function createControlRow(labelText, inputValue, inputClass, readOnly = true) {
    const row = document.createElement("div");
    row.className = "control-row";

    const input = document.createElement("input");
    input.type = "text";
    input.value = Array.isArray(inputValue) ? inputValue.join(", ") : inputValue || "";
    input.className = `control-input ${inputClass}`;
    input.readOnly = readOnly;
    row.appendChild(input);

    if (readOnly) {
        const button = document.createElement("button");
        button.type = "button";
        button.className = "control-button";
        button.textContent = labelText;
        row.appendChild(button);
    }

    return row;
}

function createToggleRow(operation) {
    const row = document.createElement("div");
    row.className = "control-row toggle-row";

    const label = document.createElement("label");
    label.className = "control-label";
    label.textContent = "Mode";
    row.appendChild(label);

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "control-toggle";
    toggle.textContent = operation.toggle_mode || operation.toggleMode || "Orifice Size";
    toggle.addEventListener("click", function () {
        const current = toggle.textContent === "Orifice Size" ? "Target Velocity" : "Orifice Size";
        toggle.textContent = current;
        updateFloatRowUnit(toggle, row);
    });
    row.appendChild(toggle);

    return row;
}

function createFloatInputRow(operation) {
    const row = document.createElement("div");
    row.className = "control-row float-row";

    const toggle = document.createElement("button");
    toggle.type = "button";
    toggle.className = "control-toggle mode-toggle";
    toggle.textContent = operation.toggle_mode || operation.toggleMode || "Orifice Size";
    toggle.addEventListener("click", function () {
        const current = toggle.textContent === "Orifice Size" ? "Target Velocity" : "Orifice Size";
        toggle.textContent = current;
        updateFloatRowUnit(toggle, row);
    });
    row.appendChild(toggle);

    const input = document.createElement("input");
    input.type = "number";
    input.step = "any";
    input.value = operation.orifice_size || operation.orificeSize || operation.target_velocity || operation.targetVelocity || "";
    input.className = "control-input float-input";
    row.appendChild(input);

    const units = document.createElement("span");
    units.className = "control-units";
    const mode = operation.toggle_mode || operation.toggleMode || "Orifice Size";
    units.textContent = mode === "Target Velocity" ? "fps" : "in";
    row.appendChild(units);

    row.dataset.toggleMode = mode;
    return row;
}

function updateFloatRowUnit(toggle, row) {
    const units = row.querySelector(".control-units");
    if (units) {
        units.textContent = toggle.textContent === "Target Velocity" ? "fps" : "in";
    }
    row.dataset.toggleMode = toggle.textContent;
}

function selectSequenceTab(sequenceName) {
    const tabButtons = document.querySelectorAll(".sequence-tab-button");
    const panels = document.querySelectorAll(".sequence-panel");

    tabButtons.forEach((button) => {
        button.classList.toggle("active", button.dataset.sequenceName === sequenceName);
    });

    panels.forEach((panel) => {
        panel.classList.toggle("active", panel.dataset.sequenceName === sequenceName);
    });
}

function displayPointLayer(layerType, geojson) {
    const layerGroup = uploadedLayerGroups[layerType];

    if (!layerGroup) {
        return;
    }

    if (layerType === 'valves') {
        clearSelectedValveMarker();
        originalValveLocationMarker = null;
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

    const icon = createValveIcon(color, false);

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

    marker.on('click', function () {
        const activeToolbar = document.querySelector('.sidebar-mode-button.active')?.getAttribute('data-toolbar-target');
        if (activeToolbar !== 'valves') {
            return;
        }
        selectValveMarker(marker);
    });

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
            if (selectedValveMarker === marker) {
                renderSelectedValveOriginalLocation(marker);
            }
        });
    } else {
        // ensure no dragging handlers are active
        marker.off('dragend');
    }

    return marker;
}

function createValveIcon(color, selected) {
    const border = selected ? "2px solid #ffffff" : "1px solid #222222";
    const size = selected ? 16 : 12;
    return L.divIcon({
        className: "",
        html: `<div class="map-valve-marker" style="background:${color}; border:${border}; width:${size}px; height:${size}px;"></div>`,
        iconSize: [size, size],
        iconAnchor: [size / 2, size / 2]
    });
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

function selectValveMarker(marker) {
    if (!marker) {
        return;
    }

    // reset previous selection
    if (selectedValveMarker && selectedValveMarker !== marker) {
        const prevProps = selectedValveMarker.feature?.properties || {};
        selectedValveMarker.setIcon(createValveIcon(prevProps.status === 'reopen' ? '#0066ff' : prevProps.status === 'close' ? '#e00000' : '#d4ff00', false));
    }

    selectedValveMarker = marker;
    const props = marker.feature?.properties || {};
    const statusColor = props.status === 'reopen' ? '#0066ff' : props.status === 'close' ? '#e00000' : '#d4ff00';
    marker.setIcon(createValveIcon(statusColor, true));

    renderSelectedValveOriginalLocation(marker);
}

function clearSelectedValveMarker() {
    if (selectedValveMarker) {
        const props = selectedValveMarker.feature?.properties || {};
        const statusColor = props.status === 'reopen' ? '#0066ff' : props.status === 'close' ? '#e00000' : '#d4ff00';
        selectedValveMarker.setIcon(createValveIcon(statusColor, false));
        selectedValveMarker = null;
    }

    if (originalValveLocationMarker) {
        map.removeLayer(originalValveLocationMarker);
        originalValveLocationMarker = null;
    }
}

function renderSelectedValveOriginalLocation(marker) {
    if (originalValveLocationMarker) {
        map.removeLayer(originalValveLocationMarker);
        originalValveLocationMarker = null;
    }

    const activeToolbar = document.querySelector('.sidebar-mode-button.active')?.getAttribute('data-toolbar-target');
    if (activeToolbar !== 'valves') {
        return;
    }

    const props = marker.feature?.properties || {};
    let originalLocation = props.original_location;
    if (typeof originalLocation === 'string') {
        try {
            originalLocation = JSON.parse(originalLocation);
        } catch (e) {
            originalLocation = null;
        }
    }

    if (!originalLocation || !Array.isArray(originalLocation) || originalLocation.length < 2) {
        return;
    }

    const latlng = L.latLng(originalLocation[1], originalLocation[0]);
    originalValveLocationMarker = L.circleMarker(latlng, {
        radius: 8,
        fillColor: '#888888',
        fillOpacity: 0.5,
        color: '#444444',
        weight: 2,
        opacity: 0.9
    }).addTo(map);
}

async function snapAllValvesToPipes() {
    const snapValvesBtn = document.getElementById('snapValvesBtn');
    const snapStatus = document.getElementById('valvesSnapStatus');
    if (!snapValvesBtn || !snapStatus) {
        return;
    }

    snapValvesBtn.disabled = true;
    snapStatus.textContent = 'Snapping valves to closest pipes...';
    snapStatus.classList.remove('error');

    try {
        const response = await fetch('/snap_valves', {
            method: 'POST'
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.message || 'Failed to snap valves.');
        }

        displayPointLayer('valves', data.geojson);
        snapStatus.textContent = data.message || 'Valves snapped successfully.';
        valvesLoaded = true;
        updateSnapValvesButtonState();
    } catch (error) {
        console.error(error);
        snapStatus.textContent = error.message;
        snapStatus.classList.add('error');
    } finally {
        if (snapValvesBtn) {
            snapValvesBtn.disabled = !(modelLoaded && valvesLoaded);
        }
    }
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