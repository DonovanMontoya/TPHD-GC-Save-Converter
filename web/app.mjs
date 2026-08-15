import { gciToTphd, tphdToGci } from "./converter.mjs";

const form = document.querySelector("#converter-form");
const status = document.querySelector("#status");
let direction = "forward";

for (const button of document.querySelectorAll("[data-direction]")) {
  button.addEventListener("click", () => {
    direction = button.dataset.direction;
    document.querySelectorAll("[data-direction]").forEach((item) => item.classList.toggle("active", item === button));
    const reverse = direction === "reverse";
    document.querySelector("#source-title").textContent = reverse ? "GameCube save" : "TPHD slot";
    document.querySelector("#source-help").textContent = reverse ? "Choose a checksum-valid Twilight Princess .gci" : "Choose one checksum-valid ZTPxx.dat file";
    document.querySelector("#template-title").textContent = reverse ? "TPHD template" : "GameCube template";
    document.querySelector("#template-help").textContent = reverse ? "An existing checksum-valid ZTPxx.dat preserves HD-only state" : "Your existing NTSC-U Twilight Princess .gci";
    document.querySelector("#reference-card").hidden = reverse;
    document.querySelector("#reference-slot-wrap").hidden = reverse;
    document.querySelector("#direction-notice").innerHTML = reverse
      ? "<strong>Experimental reverse conversion:</strong> options, location/runtime data, and the HD-only tail stay inherited from your TPHD template. Back up your original save before testing."
      : "<strong>Forward conversion:</strong> Safe mode preserves the GC template’s native location. For the published dungeon pack, the command-line curated-reference workflow remains the most complete option.";
    status.textContent = "";
  });
}

for (const input of document.querySelectorAll('input[type="file"]')) {
  input.addEventListener("change", () => {
    input.closest(".file-card").querySelector(".file-name").textContent = input.files[0]?.name ?? "Choose file";
  });
}

async function bytes(input) {
  if (!input.files[0]) throw new Error("Choose every required file first");
  return new Uint8Array(await input.files[0].arrayBuffer());
}

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
    const source = await bytes(document.querySelector("#source"));
    const template = await bytes(document.querySelector("#template"));
    const profile = document.querySelector("#profile").value;
    const slot = Number(document.querySelector("#slot").value);
    let output;
    let filename;
    if (direction === "forward") {
      const referenceInput = document.querySelector("#reference");
      const reference = referenceInput.files[0] ? await bytes(referenceInput) : null;
      output = tphdToGci(source, template, { profile, slot, reference, referenceSlot: Number(document.querySelector("#reference-slot").value) });
      filename = `converted-quest-log-${slot + 1}.gci`;
    } else {
      output = gciToTphd(source, template, { profile, slot });
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
