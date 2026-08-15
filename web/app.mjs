import { detectFormat, gcSlotSummary, gciToTphd, profileCoverage, tphdToGci } from "./converter.mjs";

const form = document.querySelector("#converter-form");
const status = document.querySelector("#status");
const outcome = document.querySelector("#outcome");
const convert = document.querySelector("button.convert");
const sourceInput = document.querySelector("#source");
const destinationInput = document.querySelector("#destination");
const profileSelect = document.querySelector("#profile");
const slotSelect = document.querySelector("#slot");

const FORMAT_LABELS = { tphd: "Twilight Princess HD save", gc: "GameCube save" };
const loaded = { source: null, destination: null };

function percent(profile) {
  return `${Math.round(profileCoverage(profile) * 100)}%`;
}

// The destination supplies every byte the mapping table does not write, so the
// share it contributes is the honest way to describe what a profile does.
function describeProfile() {
  const profile = profileSelect.value;
  const share = percent(profile);
  const note = {
    safe: "Only proven mappings. Your destination save keeps its location and story progress.",
    balanced: "Experimental. Adds inventory, item flags, and counts.",
    progress: "Experimental and highest risk. Adds stage memory, visited rooms, and event flags.",
  }[profile];
  document.querySelector("#profile-note").textContent = `Writes ${share} of the quest log; the rest comes from your destination save. ${note}`;
}

function fillSlots(select, data) {
  const summary = data ? gcSlotSummary(data) : null;
  for (const option of select.options) {
    const entry = summary?.[Number(option.value)];
    option.textContent = entry?.usable ? `Quest Log ${entry.slot + 1} — ${entry.name}` : `Quest Log ${Number(option.value) + 1}`;
    option.disabled = Boolean(summary) && !entry.usable && select === slotSelect;
  }
  const firstUsable = summary?.find((entry) => entry.usable);
  if (firstUsable) select.value = String(firstUsable.slot);
}

function refresh() {
  const source = loaded.source;
  const destination = loaded.destination;
  const direction = source?.format === "gc" ? "reverse" : "forward";
  const wanted = direction === "forward" ? "gc" : "tphd";

  document.querySelector("#destination-title").textContent =
    wanted === "gc" ? "The GameCube save it gets merged into" : "The TPHD save it gets merged into";
  document.querySelector("#destination-help").textContent = source
    ? wanted === "gc"
      ? "Your own Twilight Princess .gci. Its location and progress are kept; your HD stats are written into it."
      : "Your own checksum-valid ZTPxx.dat. It keeps HD-only state that the GameCube save has no equivalent for."
    : "Pick your file above first.";
  document.querySelector("#how-to-gci").hidden = wanted !== "gc";
  document.querySelector("#reference-wrap").hidden = direction !== "forward";

  // Only the GC side has selectable quest logs, in either direction.
  fillSlots(slotSelect, direction === "forward" ? destination?.data : source?.data);

  status.textContent = "";
  status.className = "";
  describeProfile();

  if (!source) {
    outcome.textContent = "Choose both files to continue.";
  } else if (!destination) {
    outcome.textContent = `Detected a ${FORMAT_LABELS[source.format]}. Now add the ${FORMAT_LABELS[wanted]} to merge it into.`;
  } else if (destination.format !== wanted) {
    outcome.textContent = `That second file is a ${FORMAT_LABELS[destination.format]}. This direction needs a ${FORMAT_LABELS[wanted]}.`;
  } else {
    const target = direction === "forward" ? "GameCube .gci" : "TPHD ZTPxx.dat";
    outcome.textContent = `Ready — ${percent(profileSelect.value)} of your ${FORMAT_LABELS[source.format]} will be written into a copy of your ${target}.`;
  }
  outcome.className = source && destination && destination.format !== wanted ? "outcome error" : "outcome";
  convert.disabled = !(source && destination && destination.format === wanted);
}

async function read(input, key) {
  const file = input.files[0];
  input.closest(".file-card").querySelector(".file-name").textContent = file?.name ?? "Choose file…";
  if (!file) {
    loaded[key] = null;
    return;
  }
  const data = new Uint8Array(await file.arrayBuffer());
  const format = detectFormat(data);
  loaded[key] = format ? { data, format } : null;
  if (!format) {
    status.className = "error";
    status.textContent = `${file.name} is not a recognised save file. Expected a 0xE00-byte ZTPxx.dat or a Twilight Princess .gci.`;
  }
}

sourceInput.addEventListener("change", async () => {
  await read(sourceInput, "source");
  refresh();
});
destinationInput.addEventListener("change", async () => {
  await read(destinationInput, "destination");
  refresh();
});
profileSelect.addEventListener("change", refresh);

document.querySelector("#reference").addEventListener("change", (event) => {
  event.target.closest(".file-card").querySelector(".file-name").textContent = event.target.files[0]?.name ?? "Choose file…";
});

function download(data, name) {
  const url = URL.createObjectURL(new Blob([data], { type: "application/octet-stream" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  status.className = "working";
  status.textContent = "Validating checksums and converting…";
  try {
    const profile = profileSelect.value;
    const slot = Number(slotSelect.value);
    let output;
    let filename;
    if (loaded.source.format === "tphd") {
      const referenceInput = document.querySelector("#reference");
      const reference = referenceInput.files[0] ? new Uint8Array(await referenceInput.files[0].arrayBuffer()) : null;
      const referenceSlot = Number(document.querySelector("#reference-slot").value);
      output = tphdToGci(loaded.source.data, loaded.destination.data, { profile, slot, reference, referenceSlot });
      filename = `converted-quest-log-${slot + 1}.gci`;
    } else {
      output = gciToTphd(loaded.source.data, loaded.destination.data, { profile, slot });
      filename = `ZTP0${slot}.dat`;
    }
    download(output, filename);
    status.className = "success";
    status.textContent = `Done — ${filename} passed structural and checksum validation.`;
  } catch (error) {
    status.className = "error";
    status.textContent = error instanceof Error ? error.message : String(error);
  }
});

refresh();
