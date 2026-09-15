let map;
let modelPipeLayer;
let uploadedLayerGroups = { valves: null, hydrants: null };
let pendingModelFile = null;
let modelLoaded = false;
let hydrantsLoaded = false;
let valvesLoaded = false;
let selectedValveMarker = null;
let originalValveLocationMarker = null;
let currentSequences = [];
let activeSequenceIndex = 0;
let confirmModalResolve = null;
let selectedModelHour = 0;
let flushOptions = {};

const dragState = {
    type: null,
    sequenceIndex: null,
    operationIndex: null
};

const PIPE_DIAMETER_PALETTE = [
    "#EAF6FF",
    "#A7D8FF",
    "#7ED6A8",
    "#F7D26A",
    "#F28E5B"
];

const PIPE_DIAMETER_STEP_IN_INCHES = 6;

document.addEventListener("DOMContentLoaded", function () {
    initializeTabs();
    initializeSidebarModeButtons();
    initializeMap();
    initializeToolbar();
    initializeOptionsToolbar();
    initializeModelUpload();
    initializeLayerUpload();
    initializeSequenceDialogs();
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

let renameModalResolve = null;

function initializeSequenceDialogs() {
    const confirmModal = document.getElementById('confirmModal');
    const closeConfirmModal = document.getElementById('closeConfirmModal');
    const cancelConfirmModal = document.getElementById('cancelConfirmModal');
    const confirmConfirmModal = document.getElementById('confirmConfirmModal');

    const renameModal = document.getElementById('renameModal');
    const closeRenameModal = document.getElementById('closeRenameModal');
    const cancelRenameModal = document.getElementById('cancelRenameModal');
    const confirmRenameModal = document.getElementById('confirmRenameModal');
    const renameModalTitle = document.getElementById('renameModalTitle');
    const renameModalMessage = document.getElementById('renameModalMessage');
    const renameModalInput = document.getElementById('renameModalInput');
    const renameModalError = document.getElementById('renameModalError');

    const runAllSequencesBtn = document.getElementById('runAllSequencesBtn');
    const runCurrentSequenceBtn = document.getElementById('runCurrentSequenceBtn');

    if (!confirmModal || !closeConfirmModal || !cancelConfirmModal || !confirmConfirmModal || !renameModal || !closeRenameModal || !cancelRenameModal || !confirmRenameModal || !renameModalTitle || !renameModalMessage || !renameModalInput || !renameModalError) {
        return;
    }

    function closeModal() {
        confirmModal.classList.add('hidden');
        if (confirmModalResolve) {
            confirmModalResolve(false);
            confirmModalResolve = null;
        }
    }

    function closeRename() {
        renameModal.classList.add('hidden');
        renameModalError.textContent = '';
        if (renameModalResolve) {
            renameModalResolve(null);
            renameModalResolve = null;
        }
    }

    closeConfirmModal.addEventListener('click', closeModal);
    cancelConfirmModal.addEventListener('click', closeModal);
    confirmConfirmModal.addEventListener('click', function () {
        confirmModal.classList.add('hidden');
        if (confirmModalResolve) {
            confirmModalResolve(true);
            confirmModalResolve = null;
        }
    });

    closeRenameModal.addEventListener('click', closeRename);
    cancelRenameModal.addEventListener('click', closeRename);
    confirmRenameModal.addEventListener('click', function () {
        const newName = renameModalInput.value.trim();
        if (!newName) {
            renameModalError.textContent = 'Please enter a name before saving.';
            return;
        }
        renameModal.classList.add('hidden');
        if (renameModalResolve) {
            renameModalResolve(newName);
            renameModalResolve = null;
        }
    });

    renameModal.addEventListener('click', function (event) {
        if (event.target === renameModal) {
            closeRename();
        }
    });

    confirmModal.addEventListener('click', function (event) {
        if (event.target === confirmModal) {
            closeModal();
        }
    });

    renameModalInput.addEventListener('keydown', function (event) {
        if (event.key === 'Enter') {
            event.preventDefault();
            confirmRenameModal.click();
        }
    });

    function showRenameDialog(title, message, currentName) {
        renameModalTitle.textContent = title;
        renameModalMessage.textContent = message;
        renameModalInput.value = currentName || '';
        renameModalError.textContent = '';
        renameModal.classList.remove('hidden');
        renameModalInput.focus();

        return new Promise((resolve) => {
            renameModalResolve = resolve;
        });
    }

    async function sendSequencesToBackend(url, sequences, button, statusMessage) {
        if (!Array.isArray(sequences) || sequences.length === 0) {
            setSequenceStatus('No sequences are available to run.', true);
            return;
        }

        if (button) {
            button.disabled = true;
        }
        setSequenceStatus(statusMessage, false);

        try {
            const response = await fetch(url, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ sequences: sequences })
            });
            const data = await response.json();

            if (!response.ok || !data.success) {
                throw new Error(data.message || 'Failed to send sequences to the backend.');
            }

            setSequenceStatus(data.message || 'Sequences sent successfully.', false);
        } catch (error) {
            console.error(error);
            setSequenceStatus(error.message || 'Failed to send sequences.', true);
        } finally {
            if (button) {
                button.disabled = false;
            }
        }
    }

    runAllSequencesBtn?.addEventListener('click', async function () {
        const sequencesToRun = currentSequences;
        await sendSequencesToBackend('/run_sequences', sequencesToRun, runAllSequencesBtn, 'Sending all sequences...');
    });

    runCurrentSequenceBtn?.addEventListener('click', async function () {
        const currentSequence = currentSequences[activeSequenceIndex];
        const sequencesToRun = currentSequence ? [currentSequence] : [];
        await sendSequencesToBackend('/run_sequence', sequencesToRun, runCurrentSequenceBtn, 'Sending current sequence...');
    });

    window.showRenameDialog = showRenameDialog;
}

function showConfirmDialog(message) {
    const confirmModal = document.getElementById('confirmModal');
    const confirmModalMessage = document.getElementById('confirmModalMessage');

    if (!confirmModal || !confirmModalMessage) {
        return Promise.resolve(false);
    }

    confirmModalMessage.textContent = message;
    confirmModal.classList.remove('hidden');

    return new Promise((resolve) => {
        confirmModalResolve = resolve;
    });
}

async function saveSequencesToServer() {
    try {
        await fetch('/save_sequences', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ sequences: currentSequences })
        });
    } catch (error) {
        console.error('Failed to save sequences:', error);
    }
}

function addSequence() {
    const nextIndex = currentSequences.length + 1;
    const newSequence = {
        name: `Sequence ${nextIndex}`,
        operations: []
    };

    currentSequences.push(newSequence);
    renderSequences(currentSequences, `Sequence ${nextIndex} added.`);
    selectSequenceTab(currentSequences.length - 1);
}

function addOperation(sequenceIndex) {
    const sequence = currentSequences[sequenceIndex];
    if (!sequence) {
        return;
    }

    const nextOpIndex = sequence.operations.length + 1;
    sequence.operations.push({
        name: `Operation ${nextOpIndex}`,
        open_valves: [],
        close_valves: [],
        open_hydrants: [],
        orifice_size: "",
        target_velocity: "",
        toggle_mode: "Orifice Size",
        map_message: ""
    });

    renderSequences(currentSequences, `Added operation to ${sequence.name}.`);
    selectSequenceTab(sequenceIndex);
}

async function deleteSequence(sequenceIndex) {
    const sequence = currentSequences[sequenceIndex];
    if (!sequence) {
        return;
    }

    const confirmed = await showConfirmDialog(`Delete sequence "${sequence.name}"? This cannot be undone.`);
    if (!confirmed) {
        return;
    }

    currentSequences.splice(sequenceIndex, 1);
    if (activeSequenceIndex >= currentSequences.length) {
        activeSequenceIndex = Math.max(0, currentSequences.length - 1);
    }

    renderSequences(currentSequences, `Deleted sequence ${sequence.name}.`);
    if (currentSequences.length > 0) {
        selectSequenceTab(activeSequenceIndex);
    }
}

async function deleteOperation(sequenceIndex, operationIndex) {
    const sequence = currentSequences[sequenceIndex];
    if (!sequence || sequence.operations.length <= operationIndex) {
        return;
    }

    const operation = sequence.operations[operationIndex];
    const operationName = operation?.name || `Operation ${operationIndex + 1}`;
    const confirmed = await showConfirmDialog(`Delete operation "${operationName}"? This cannot be undone.`);
    if (!confirmed) {
        return;
    }

    sequence.operations.splice(operationIndex, 1);
    renderSequences(currentSequences, `Deleted operation from ${sequence.name}.`);
    selectSequenceTab(sequenceIndex);
}

function renameSequence(sequenceIndex, newName) {
    const sequence = currentSequences[sequenceIndex];
    if (!sequence) {
        return;
    }

    sequence.name = newName || sequence.name;
    renderSequences(currentSequences, `Renamed sequence to ${sequence.name}.`);
    selectSequenceTab(sequenceIndex);
}

function renameOperation(sequenceIndex, operationIndex, newName) {
    const operation = currentSequences[sequenceIndex]?.operations[operationIndex];
    if (!operation) {
        return;
    }

    operation.name = newName || operation.name;
    renderSequences(currentSequences, `Renamed operation to ${operation.name}.`);
    selectSequenceTab(sequenceIndex);
}

function moveSequenceUp(sequenceIndex) {
    if (sequenceIndex <= 0 || sequenceIndex >= currentSequences.length) {
        return;
    }

    reorderSequences(sequenceIndex, sequenceIndex - 1);
}

function moveSequenceDown(sequenceIndex) {
    if (sequenceIndex < 0 || sequenceIndex >= currentSequences.length - 1) {
        return;
    }

    reorderSequences(sequenceIndex, sequenceIndex + 1);
}

function moveOperationUp(sequenceIndex, operationIndex) {
    const sequence = currentSequences[sequenceIndex];
    if (!sequence || operationIndex <= 0 || operationIndex >= sequence.operations.length) {
        return;
    }

    reorderOperations(sequenceIndex, operationIndex, operationIndex - 1);
}

function moveOperationDown(sequenceIndex, operationIndex) {
    const sequence = currentSequences[sequenceIndex];
    if (!sequence || operationIndex < 0 || operationIndex >= sequence.operations.length - 1) {
        return;
    }

    reorderOperations(sequenceIndex, operationIndex, operationIndex + 1);
}

function reorderSequences(fromIndex, toIndex) {
    if (fromIndex === toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= currentSequences.length || toIndex >= currentSequences.length) {
        return;
    }

    const [moved] = currentSequences.splice(fromIndex, 1);
    currentSequences.splice(toIndex, 0, moved);
    renderSequences(currentSequences, `Reordered sequences.`);
    selectSequenceTab(toIndex);
}

function reorderOperations(sequenceIndex, fromIndex, toIndex) {
    const sequence = currentSequences[sequenceIndex];
    if (!sequence || fromIndex === toIndex || fromIndex < 0 || toIndex < 0 || fromIndex >= sequence.operations.length || toIndex >= sequence.operations.length) {
        return;
    }

    const [moved] = sequence.operations.splice(fromIndex, 1);
    sequence.operations.splice(toIndex, 0, moved);
    renderSequences(currentSequences, `Reordered operations in ${sequence.name}.`);
    selectSequenceTab(sequenceIndex);
}

function handleSequenceDragStart(event, sequenceIndex) {
    dragState.type = 'sequence';
    dragState.sequenceIndex = sequenceIndex;
    dragState.operationIndex = null;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', JSON.stringify(dragState));
}

function handleOperationDragStart(event, sequenceIndex, operationIndex) {
    dragState.type = 'operation';
    dragState.sequenceIndex = sequenceIndex;
    dragState.operationIndex = operationIndex;
    event.dataTransfer.effectAllowed = 'move';
    event.dataTransfer.setData('text/plain', JSON.stringify(dragState));
}

function handleDrop(event, sequenceIndex, operationIndex) {
    event.preventDefault();
    const payload = event.dataTransfer.getData('text/plain');
    if (!payload) {
        return;
    }

    try {
        const dragged = JSON.parse(payload);
        if (dragged.type === 'sequence') {
            reorderSequences(dragged.sequenceIndex, sequenceIndex);
        } else if (dragged.type === 'operation' && dragged.sequenceIndex === sequenceIndex) {
            reorderOperations(sequenceIndex, dragged.operationIndex, operationIndex);
        }
    } catch (error) {
        console.error('Failed to parse drag payload', error);
    }
}

function handleDragOver(event) {
    event.preventDefault();
    event.dataTransfer.dropEffect = 'move';
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

    buildPipeDiameterLegend();

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

function getPipeDiameterColor(diameterInches) {
    const numericDiameter = Number(diameterInches);

    if (!Number.isFinite(numericDiameter) || numericDiameter <= 0) {
        return "#D7DEE8";
    }

    const paletteIndex = Math.min(
        PIPE_DIAMETER_PALETTE.length - 1,
        Math.floor(numericDiameter / PIPE_DIAMETER_STEP_IN_INCHES)
    );

    return PIPE_DIAMETER_PALETTE[paletteIndex % PIPE_DIAMETER_PALETTE.length];
}

function buildPipeDiameterLegend() {
    const mapElement = document.getElementById("map");
    if (!mapElement) {
        return;
    }

    let legend = document.getElementById("pipeDiameterLegend");
    if (!legend) {
        legend = document.createElement("div");
        legend.id = "pipeDiameterLegend";
        legend.className = "pipe-legend";
        mapElement.appendChild(legend);
    }

    const bands = [
        { label: "≤ 6 in", color: PIPE_DIAMETER_PALETTE[0] },
        { label: "6-12 in", color: PIPE_DIAMETER_PALETTE[1] },
        { label: "12-18 in", color: PIPE_DIAMETER_PALETTE[2] },
        { label: "18-24 in", color: PIPE_DIAMETER_PALETTE[3] },
        { label: "> 24 in", color: PIPE_DIAMETER_PALETTE[4] }
    ];

    legend.innerHTML = `
        <div class="pipe-legend-title">Pipe diameter</div>
        ${bands.map((band) => `
            <div class="pipe-legend-row">
                <span class="pipe-legend-swatch" style="background:${band.color};"></span>
                <span>${band.label}</span>
            </div>
        `).join("")}
    `;
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
        const timestepInput = document.getElementById('epsgTimestepInput');
        let timestepVal = 0;
        if (timestepInput) {
            const parsed = parseFloat(timestepInput.value);
            timestepVal = Number.isFinite(parsed) ? Math.round(parsed * 4) / 4 : 0;
        }

        if (!epsgValue) {
            epsgError.textContent = "EPSG code is required.";
            return;
        }

        const modelCrs = epsgValue.toUpperCase().startsWith("EPSG:")
            ? epsgValue
            : `EPSG:${epsgValue}`;

        hideEpsgModal();
        submitModelFile(pendingModelFile, modelCrs, timestepVal);
    });
}

function initializeOptionsToolbar() {
    const statusDiv = document.getElementById('optionsStatus');

    // element references
    const el = (id) => document.getElementById(id);
    const inputs = {
        modelTimestep: el('modelTimestepInput'),
        presDropWarningLimit: el('presDropWarningLimitInput'),
        defaultOrificeDiam: el('defaultOrificeDiamInput'),
        volumeTurnovers: el('volumeTurnoversInput'),
        maxFlushDiam: el('maxFlushDiamInput'),
        maxFlushLength: el('maxFlushLengthInput'),
        lateralDiam: el('lateralDiamInput'),
        lateralRoughness: el('lateralRoughnessInput'),
        outletCoeff: el('outletCoeffInput'),
        hoseLength: el('hoseLengthInput'),
        hoseRoughness: el('hoseRoughnessInput'),
        minFlushVel: el('minFlushVelInput'),
        maxFlushVel: el('maxFlushVelInput'),
        minResPres: el('minResPresInput'),
        searchDist: el('searchDistInput'),
        startVelToFlushingVelRatio: el('startVelToFlushingVelRatioInput')
    };

    function parseNumber(value, fallback) {
        const v = parseFloat(value);
        return Number.isFinite(v) ? v : fallback;
    }

    function readOptions() {
        const opts = {
            pres_drop_warning_limit: parseNumber(inputs.presDropWarningLimit?.value, 10.0),
            default_orifice_diam: parseNumber(inputs.defaultOrificeDiam?.value, 2.5),
            volume_turnovers: parseNumber(inputs.volumeTurnovers?.value, 3.0),
            max_flush_diam: parseNumber(inputs.maxFlushDiam?.value, 20.0),
            max_flush_length: parseNumber(inputs.maxFlushLength?.value, 5280),
            lateral_diam: parseNumber(inputs.lateralDiam?.value, 5.99),
            lateral_roughness: parseNumber(inputs.lateralRoughness?.value, 1.0),
            outlet_coeff: parseNumber(inputs.outletCoeff?.value, 0.9),
            hose_length: parseNumber(inputs.hoseLength?.value, 15.0),
            hose_roughness: parseNumber(inputs.hoseRoughness?.value, 1.0),
            min_flush_vel: parseNumber(inputs.minFlushVel?.value, 5.0),
            max_flush_vel: parseNumber(inputs.maxFlushVel?.value, 10.0),
            min_res_pres: parseNumber(inputs.minResPres?.value, 20.0),
            search_dist: parseNumber(inputs.searchDist?.value, 120.0),
            start_vel_to_flushing_vel_ratio: parseNumber(inputs.startVelToFlushingVelRatio?.value, 3.0)
        };

        // model timestep handled separately
        if (inputs.modelTimestep) {
            let mt = parseNumber(inputs.modelTimestep.value, 0);
            mt = Math.max(0, Math.min(23.75, Math.round(mt * 4) / 4));
            selectedModelHour = mt;
            opts.model_timestep = mt;
        } else {
            opts.model_timestep = selectedModelHour;
        }

        flushOptions = opts;

        if (statusDiv) {
            statusDiv.textContent = `Pres drop limit: ${opts.pres_drop_warning_limit}, Orifice(in): ${opts.default_orifice_diam}, Hose(ft): ${opts.hose_length}`;
        }

        return opts;
    }

    // initialize values from DOM
    readOptions();

    // attach listeners
    Object.values(inputs).forEach((inputEl) => {
        if (!inputEl) return;
        inputEl.addEventListener('input', function () {
            readOptions();
        });
    });

    window.getSelectedModelHour = function () {
        return selectedModelHour;
    };

    window.getFlushOptions = function () {
        return flushOptions;
    };
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
    const addSequenceBtn = document.getElementById("addSequenceBtn");

    if (sequenceTabContainer) {
        sequenceTabContainer.addEventListener("click", function (event) {
            const button = event.target.closest(".sequence-tab-button");
            if (!button) {
                return;
            }
            selectSequenceTab(Number(button.dataset.sequenceIndex));
        });
    }

    if (addSequenceBtn) {
        addSequenceBtn.addEventListener("click", addSequence);
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
    const epsgTimestepInput = document.getElementById("epsgTimestepInput");

    if (!modal || !epsgInput || !epsgError) {
        return;
    }

    modal.classList.add("hidden");
    epsgInput.value = "6625";
    if (epsgTimestepInput) epsgTimestepInput.value = "0";
    epsgError.textContent = "";
}

async function submitModelFile(file, modelCrs, modelTimestep=0) {
    if (!file) {
        setModelStatus("No file selected.", true);
        return;
    }

    const loadModelBtn = document.getElementById("loadModelBtn");
    const formData = new FormData();

    formData.append("inp_file", file);
    formData.append("model_crs", modelCrs);
    formData.append("model_timestep", String(modelTimestep));

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
        // If server returned the model_timestep used for the snapshot, update options toolbar input
        try {
            const optInput = document.getElementById('modelTimestepInput');
            if (optInput && data.model_timestep !== undefined && data.model_timestep !== null) {
                optInput.value = String(data.model_timestep);
                optInput.dispatchEvent(new Event('input'));
            }
        } catch (e) {
            console.warn('Failed to update options timestep from server response', e);
        }
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
    const props = feature?.properties || {};
    const diameterInches = Number(props.diameter);

    return {
        color: getPipeDiameterColor(diameterInches),
        weight: 3,
        opacity: 1.0
    };
}

function onEachModelPipe(feature, layer) {
    const props = feature.properties || {};
    const diameterValue = props.diameter == null || props.diameter === "" ? "" : formatPopupNumber(props.diameter);

    const popupHtml = `
        <strong>${props.name || props.id || "Pipe"}</strong><br>
        Start Node: ${props.start_node || ""}<br>
        End Node: ${props.end_node || ""}<br>
        Length: ${formatPopupNumber(props.length)}<br>
        Diameter: ${diameterValue}${diameterValue ? " in" : ""}
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

    currentSequences = Array.isArray(sequences) ? sequences : [];
    sequenceTabs.innerHTML = "";
    sequencePanels.innerHTML = "";

    if (!Array.isArray(currentSequences) || currentSequences.length === 0) {
        setSequenceStatus(message || "No sequences loaded.", false);
        return;
    }

    currentSequences.forEach((sequence, index) => {
        const sequenceName = sequence.name || `Sequence ${index + 1}`;

        const item = document.createElement("div");
        item.className = "sequence-item";
        item.dataset.sequenceIndex = index;
        item.setAttribute('draggable', 'true');
        item.addEventListener('dragstart', function (event) {
            handleSequenceDragStart(event, index);
        });
        item.addEventListener('drop', function (event) {
            handleDrop(event, index, null);
        });
        item.addEventListener('dragover', handleDragOver);

        const headerRow = document.createElement("div");
        headerRow.className = "sequence-item-header";

        const tabButton = document.createElement("button");
        tabButton.type = "button";
        tabButton.className = "sequence-tab-button";
        tabButton.dataset.sequenceIndex = index;
        tabButton.textContent = sequenceName;
        tabButton.addEventListener("click", function () {
            selectSequenceTab(index);
        });

        const nameControls = document.createElement('div');
        nameControls.className = 'sequence-name-controls';

        const editButton = document.createElement('button');
        editButton.type = 'button';
        editButton.className = 'sequence-edit-button';
        editButton.title = 'Rename sequence';
        editButton.textContent = '✎';
        editButton.addEventListener('click', async function () {
            const newName = await window.showRenameDialog('Rename Sequence', 'Enter a new sequence name below.', sequenceName);
            if (newName) {
                renameSequence(index, newName);
            }
        });

        const upButton = document.createElement('button');
        upButton.type = 'button';
        upButton.className = 'sequence-edit-button sequence-move-button';
        upButton.title = 'Move sequence up';
        upButton.textContent = '↑';
        upButton.disabled = index === 0;
        upButton.addEventListener('click', function () {
            moveSequenceUp(index);
        });

        const downButton = document.createElement('button');
        downButton.type = 'button';
        downButton.className = 'sequence-edit-button sequence-move-button';
        downButton.title = 'Move sequence down';
        downButton.textContent = '↓';
        downButton.disabled = index === currentSequences.length - 1;
        downButton.addEventListener('click', function () {
            moveSequenceDown(index);
        });

        const deleteButton = document.createElement("button");
        deleteButton.type = "button";
        deleteButton.className = "sequence-action-button sequence-delete-button";
        deleteButton.textContent = "-";
        deleteButton.addEventListener("click", function () {
            deleteSequence(index);
        });

        nameControls.appendChild(editButton);
        nameControls.appendChild(upButton);
        nameControls.appendChild(downButton);
        nameControls.appendChild(deleteButton);

        headerRow.appendChild(tabButton);
        headerRow.appendChild(nameControls);

        const panel = document.createElement("div");
        panel.className = `sequence-panel${index === activeSequenceIndex ? " active" : ""}`;
        panel.dataset.sequenceIndex = index;
        panel.addEventListener('dragover', handleDragOver);
        panel.addEventListener('drop', function (event) {
            handleDrop(event, index, (sequence.operations || []).length);
        });

        const operationsList = document.createElement('div');
        operationsList.className = 'sequence-operation-list';

        (sequence.operations || []).forEach((operation, operationIndex) => {
            const operationSection = document.createElement("div");
            operationSection.className = "sequence-operation";
            operationSection.dataset.operationIndex = operationIndex;
            operationSection.setAttribute('draggable', 'true');
            operationSection.addEventListener('dragstart', function (event) {
                handleOperationDragStart(event, index, operationIndex);
            });
            operationSection.addEventListener('drop', function (event) {
                handleDrop(event, index, operationIndex);
            });
            operationSection.addEventListener('dragover', handleDragOver);

            const operationHeader = document.createElement("div");
            operationHeader.className = "sequence-operation-header";

            const operationTitleLabel = document.createElement('span');
            operationTitleLabel.className = 'sequence-operation-name-label';
            operationTitleLabel.textContent = operation.name || `Operation ${operationIndex + 1}`;

            const operationNameGroup = document.createElement('div');
            operationNameGroup.className = 'sequence-operation-title-group';
            operationNameGroup.appendChild(operationTitleLabel);

            const opEditButton = document.createElement('button');
            opEditButton.type = 'button';
            opEditButton.className = 'sequence-edit-button';
            opEditButton.title = 'Rename operation';
            opEditButton.textContent = '✎';
            opEditButton.addEventListener('click', async function (event) {
                event.stopPropagation();
                const currentName = operation.name || `Operation ${operationIndex + 1}`;
                const newName = await window.showRenameDialog('Rename Operation', 'Enter a new operation name below.', currentName);
                if (newName) {
                    renameOperation(index, operationIndex, newName);
                }
            });

            const opUpButton = document.createElement('button');
            opUpButton.type = 'button';
            opUpButton.className = 'sequence-edit-button sequence-move-button';
            opUpButton.title = 'Move operation up';
            opUpButton.textContent = '↑';
            opUpButton.disabled = operationIndex === 0;
            opUpButton.addEventListener('click', function (event) {
                event.stopPropagation();
                moveOperationUp(index, operationIndex);
            });

            const opDownButton = document.createElement('button');
            opDownButton.type = 'button';
            opDownButton.className = 'sequence-edit-button sequence-move-button';
            opDownButton.title = 'Move operation down';
            opDownButton.textContent = '↓';
            opDownButton.disabled = operationIndex === (sequence.operations || []).length - 1;
            opDownButton.addEventListener('click', function (event) {
                event.stopPropagation();
                moveOperationDown(index, operationIndex);
            });

            const opDeleteButton = document.createElement("button");
            opDeleteButton.type = "button";
            opDeleteButton.className = "sequence-action-button sequence-delete-button";
            opDeleteButton.textContent = "-";
            opDeleteButton.addEventListener("click", function () {
                deleteOperation(index, operationIndex);
            });

            operationNameGroup.appendChild(opEditButton);
            operationNameGroup.appendChild(opUpButton);
            operationNameGroup.appendChild(opDownButton);
            operationNameGroup.appendChild(opDeleteButton);
 
            operationHeader.appendChild(operationNameGroup);

            operationHeader.addEventListener('click', function (event) {
                if (event.target.closest('button') || event.target.closest('input')) {
                    return;
                }

                const isOpen = operationSection.classList.toggle('open');
                if (isOpen) {
                    const siblingOperations = operationsList.querySelectorAll('.sequence-operation.open');
                    siblingOperations.forEach((sibling) => {
                        if (sibling !== operationSection) {
                            sibling.classList.remove('open');
                        }
                    });
                }
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
            operationsList.appendChild(operationSection);
        });

        const addOpButton = document.createElement("button");
        addOpButton.type = "button";
        addOpButton.className = "sequence-action-button sequence-add-button";
        addOpButton.textContent = "+ Add Operation";
        addOpButton.addEventListener("click", function () {
            addOperation(index);
        });

        panel.appendChild(operationsList);
        panel.appendChild(addOpButton);

        headerRow.appendChild(tabButton);
        headerRow.appendChild(nameControls);
        headerRow.appendChild(deleteButton);

        item.appendChild(headerRow);
        item.appendChild(panel);
        sequenceTabs.appendChild(item);
    });

    selectSequenceTab(activeSequenceIndex);
    saveSequencesToServer();
    setSequenceStatus(message || `Loaded ${currentSequences.length} sequence${currentSequences.length === 1 ? "" : "s"}.`, false);
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

function selectSequenceTab(sequenceIndex) {
    activeSequenceIndex = sequenceIndex;
    const items = document.querySelectorAll('.sequence-item');
    items.forEach((item) => {
        const index = Number(item.dataset.sequenceIndex);
        const isActive = index === sequenceIndex;
        const tab = item.querySelector('.sequence-tab-button');
        const panel = item.querySelector('.sequence-panel');
        if (tab) tab.classList.toggle('active', isActive);
        if (panel) panel.classList.toggle('active', isActive);
        if (!isActive) {
            panel?.querySelectorAll('.sequence-operation.open')?.forEach(op => op.classList.remove('open'));
        }
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