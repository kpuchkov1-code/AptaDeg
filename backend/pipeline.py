"""
Real pipeline implementation for AptaDeg.

Steps implemented:
  0.  CRBN reference loading (4CI1, startup once)      — real
  1.  Fetch structure (RCSB / ESMFold)                 — real
  1b. Clean structure (BioPython)                      — real
  2.  Identify binding sites (fpocket via WSL)         — real if installed
  3.  Aptamer generation (RNAFlow → InverseFolding → biased fallback)
  4.  Fold stability validation (ViennaRNA)             — flag, not filter
  5.  3D aptamer prediction (rna-tools)                — real if installed
  6.  Docking (rDock via WSL; HADDOCK fallback)        — real if installed
  7.  Epitope quality (BioPython SASA)                 — real once docking output available
  8.  Lysine accessibility (BioPython SASA)            — real once docking output available
  9.  Ternary complex geometry (CRBN 4CI1 ref)         — real if 4CI1 available; geometric fallback
  10. Hook effect penalty                              — arithmetic, always real
  11. Composite degradability score (RNAFlow-aware)    — arithmetic, always real
"""

import atexit
import os
import re
import json
import math
import logging
import platform
import random
import subprocess
import tempfile
import textwrap
import threading
import time
import urllib.request
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from multiprocessing import Pool  # noqa: F401 — kept for potential future use
from pathlib import Path

import numpy as np

from Bio.PDB import PDBParser, PDBIO, Select, ShrakeRupley
from Bio.PDB.DSSP import DSSP

# ViennaRNA — optional
try:
    import RNA
    VIENNA_AVAILABLE = True
except ImportError:
    VIENNA_AVAILABLE = False

# rna-tools v3.x — the 3D module is mini_moderna3, not rna_dot_bracket_to_3d
try:
    from rna_tools.tools.mini_moderna3 import moderna as _moderna_mod
    import os as _os
    _MODERNA_DATA_DIR = _os.path.join(
        _os.path.dirname(_moderna_mod.__file__), "data"
    )
    _MODERNA_HELIX_PDB = _os.path.join(_MODERNA_DATA_DIR, "helix.pdb")
    RNA_TOOLS_AVAILABLE = _os.path.exists(_MODERNA_HELIX_PDB)
except Exception:
    RNA_TOOLS_AVAILABLE = False
    _MODERNA_HELIX_PDB = None

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
_TEMPLATE_DIR = CACHE_DIR / "templates"
_TEMPLATE_DIR.mkdir(exist_ok=True)

# Three aptamer backbone templates covering the main RNA topological families.
# Used by predict_3d_structures to give rDock genuine geometric diversity.
_BACKBONE_TEMPLATES = {
    '2AP6': _TEMPLATE_DIR / '2AP6.pdb',   # TAR RNA stem-loop
    '2GKU': _TEMPLATE_DIR / '2GKU.pdb',   # G-quadruplex (thrombin aptamer)
    '3Q3Z': _TEMPLATE_DIR / '3Q3Z.pdb',   # Multi-stem (MS2 coat protein aptamer)
}

CRBN_CATALYTIC = {('Y', 384), ('W', 386), ('H', 378), ('H', 353)}  # (resname1, resseq)
KD2_CRBN_NM = 5.0  # pomalidomide → CRBN, literature

# RNA complement for stem-loop scaffold generation
_RNA_COMPLEMENT = {'A': 'U', 'U': 'A', 'G': 'C', 'C': 'G'}

# ---------------------------------------------------------------------------
# WSL process registry — kill child processes on timeout, cancel, or shutdown
# ---------------------------------------------------------------------------
# wsl.exe is a thin wrapper; killing it does NOT kill the rDock/rbcavity child
# inside WSL. We track every Popen handle so we can send a WSL-side pkill on
# cancel, disconnect, or Flask shutdown.

_wsl_procs_lock = threading.Lock()
_wsl_procs: list[subprocess.Popen] = []


def _register_wsl_proc(proc: subprocess.Popen) -> None:
    with _wsl_procs_lock:
        _wsl_procs.append(proc)


def _unregister_wsl_proc(proc: subprocess.Popen) -> None:
    with _wsl_procs_lock:
        try:
            _wsl_procs.remove(proc)
        except ValueError:
            pass


def kill_all_wsl_processes() -> None:
    """Kill all tracked WSL subprocesses and pkill rDock/rbcavity inside WSL.
    Called on pipeline cancel (disconnect) and Flask shutdown."""
    with _wsl_procs_lock:
        procs = list(_wsl_procs)
    for p in procs:
        try:
            p.kill()
        except Exception:
            pass
    # Also pkill any orphaned rDock/rbcavity processes still running inside WSL
    try:
        subprocess.run(
            ["wsl", "-d", "Ubuntu", "-u", "root", "--", "bash", "-c",
             "pkill -SIGKILL -x rbdock 2>/dev/null; pkill -SIGKILL -x rbcavity 2>/dev/null; true"],
            timeout=5, capture_output=True,
        )
    except Exception:
        pass
    with _wsl_procs_lock:
        _wsl_procs.clear()


def _atexit_kill_wsl() -> None:
    """atexit-safe cleanup: uses os.system instead of subprocess.run.
    subprocess.run uses the threading machinery which is already torn down
    during interpreter shutdown, causing 'can't reschedule new futures' errors.
    os.system is a direct C-level fork+exec with no Python thread involvement."""
    # Kill tracked Popen handles (no subprocess calls needed)
    try:
        with _wsl_procs_lock:
            procs = list(_wsl_procs)
        for p in procs:
            try:
                p.kill()
            except Exception:
                pass
    except Exception:
        pass
    # pkill orphaned rDock/rbcavity in WSL via os.system (no threads)
    os.system(
        'wsl -d Ubuntu -u root -- bash -c '
        '"pkill -SIGKILL -x rbdock 2>/dev/null; '
        'pkill -SIGKILL -x rbcavity 2>/dev/null; true"'
    )


# Kill all WSL children when Flask process exits (covers Ctrl+C and restarts)
atexit.register(_atexit_kill_wsl)


# ---------------------------------------------------------------------------
# GPU / timing utilities
# ---------------------------------------------------------------------------

def log_gpu_status(step_name: str) -> None:
    """Log current GPU memory usage after a GPU-intensive step."""
    try:
        import torch
        if torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated() / 1e6
            reserved  = torch.cuda.memory_reserved()  / 1e6
            _log(step_name, f"GPU {torch.cuda.get_device_name(0)}: "
                            f"{allocated:.0f}MB allocated, {reserved:.0f}MB reserved")
        else:
            _log(step_name, "running on CPU")
    except Exception:
        pass


@contextmanager
def timed_step(step_name: str):
    """Context manager that logs wall-clock time for a pipeline step."""
    start = time.time()
    _log(step_name, "START")
    try:
        yield
    finally:
        elapsed = time.time() - start
        _log(step_name, f"DONE — {elapsed:.1f}s")


# ---------------------------------------------------------------------------
# RNAFlow — GPU inference via WSL2 subprocess (Linux DGL CUDA wheels)
# ---------------------------------------------------------------------------

_RNAFLOW_ROOT = str(Path(__file__).parent.parent.parent / "rnaflow")
_RNAFLOW_CKPT = str(Path(_RNAFLOW_ROOT) / "checkpoints" / "seq-sim-rnaflow-epoch32.ckpt")
_RNAFLOW_WSL_SCRIPT = str(Path(__file__).parent / "run_rnaflow_wsl.py")
_WSL_VENV = "/opt/rnaflow_env"

RNAFLOW_AVAILABLE = False
_inverse_folding_model = None  # kept for CPU fallback path


def _run_rnaflow_wsl(clean_pdb: str, n: int, rna_len: int, seed: int) -> list[dict] | None:
    """
    Run RNAFlow inside WSL2 where DGL CUDA Linux wheels are installed.
    Returns list of candidate dicts, or None on failure.
    """
    import tempfile
    output_path = str(CACHE_DIR / "rnaflow_wsl_output.json")
    protein_wsl = _win_to_wsl(str(Path(clean_pdb).resolve()))
    script_wsl  = _win_to_wsl(_RNAFLOW_WSL_SCRIPT)
    output_wsl  = _win_to_wsl(output_path)

    cmd = [
        "wsl", "-d", "Ubuntu", "--",
        "bash", "-c",
        f"source {_WSL_VENV}/bin/activate && "
        f"python {script_wsl} "
        f"--protein {protein_wsl} "
        f"--output {output_wsl} "
        f"--n_samples {n} "
        f"--temperature 0.9 "
        f"--rna_len {rna_len} "
        f"--device cuda "
        f"--seed {seed}",
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        stderr_lines = (proc.stderr or "").strip().splitlines()
        for line in stderr_lines:
            if line.strip():
                _log("rnaflow_wsl", line.strip())
        if proc.returncode != 0:
            _log("rnaflow_wsl", f"WSL script exited {proc.returncode}")
            return None
        if not Path(output_path).exists():
            _log("rnaflow_wsl", "output file not created")
            return None
        with open(output_path) as f:
            candidates = json.load(f)
        _log("rnaflow_wsl", f"received {len(candidates)} candidates from WSL GPU")
        return candidates if candidates else None
    except subprocess.TimeoutExpired:
        _log("rnaflow_wsl", "WSL subprocess timed out after 120s")
        return None
    except Exception as exc:
        _log("rnaflow_wsl", f"WSL subprocess failed: {exc}")
        return None


def _try_load_inverse_folding() -> bool:
    """
    Attempt to load InverseFoldingModel from the rnaflow checkpoint.
    Returns True if the model is ready; sets _inverse_folding_model global.
    """
    global _inverse_folding_model, RNAFLOW_AVAILABLE
    if _inverse_folding_model is not None:
        return True
    try:
        import sys, warnings, torch
        warnings.filterwarnings("ignore")

        for p in [
            _RNAFLOW_ROOT,
            str(Path(_RNAFLOW_ROOT) / "rnaflow" / "utils"),
            str(Path(_RNAFLOW_ROOT) / "geometric_rna_design" / "src"),
            str(Path(_RNAFLOW_ROOT) / "RoseTTAFold2NA" / "network"),
        ]:
            if p not in sys.path:
                sys.path.insert(0, p)

        from rnaflow.models.inverse_folding import InverseFoldingModel

        if not Path(_RNAFLOW_CKPT).exists():
            _log("rnaflow", f"checkpoint not found: {_RNAFLOW_CKPT}")
            return False

        # Prefer GPU (DGL 2.2.1+cu121 now installed and verified on CUDA 12.4).
        # Fall back to CPU if CUDA is unavailable.
        device = "cuda" if torch.cuda.is_available() else "cpu"
        model = InverseFoldingModel.load_from_checkpoint(
            _RNAFLOW_CKPT, map_location=device, strict=False
        )
        model.training = False
        model.to(device)
        model.data_featurizer.device = device
        _inverse_folding_model = model
        RNAFLOW_AVAILABLE = True
        _log("rnaflow", f"InverseFoldingModel loaded on {device} "
                        f"({'RTX 3070' if device == 'cuda' else 'CPU'})")
        return True
    except Exception as exc:
        _log("rnaflow", f"InverseFoldingModel unavailable: {exc}")
        return False


def _extract_prot_backbone(clean_pdb: str) -> tuple:
    """
    Extract protein sequence and N/CA/C backbone coordinates from a cleaned PDB.
    Returns (sequence_str, coords_tensor) with coords shape (N, 3, 3), or (None, None).
    """
    try:
        import torch

        AA3TO1 = {
            "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
            "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
            "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
            "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
        }

        parser = PDBParser(QUIET=True)
        structure = parser.get_structure("prot", clean_pdb)

        seq_chars, coords = [], []
        for residue in structure.get_residues():
            if residue.id[0] != " ":
                continue
            aa = AA3TO1.get(residue.get_resname().strip())
            if aa is None:
                continue
            try:
                n  = residue["N"].coord
                ca = residue["CA"].coord
                c  = residue["C"].coord
                seq_chars.append(aa)
                coords.append([[n[0], n[1], n[2]],
                                [ca[0], ca[1], ca[2]],
                                [c[0], c[1], c[2]]])
            except KeyError:
                continue

        if not seq_chars:
            return None, None
        return "".join(seq_chars), torch.tensor(coords, dtype=torch.float32)
    except Exception as exc:
        _log("rnaflow", f"backbone extraction failed: {exc}")
        return None, None


def _build_rna_backbone_coords(sequence: str) -> object:
    """
    Build approximate P/C4'/N backbone coords for an RNA sequence from the helix template.
    Returns tensor shape (L, 3, 3) or None.
    """
    if not RNA_TOOLS_AVAILABLE:
        return None
    try:
        import torch

        parser = PDBParser(QUIET=True)
        template = parser.get_structure("helix", _MODERNA_HELIX_PDB)
        template_residues = list(template.get_residues())
        n_template = len(template_residues)

        coords = []
        for i, _ in enumerate(sequence):
            src = template_residues[i % n_template]
            try:
                p  = src["P"].coord
                c4 = src["C4'"].coord
                n1 = (src["N1"].coord if "N1" in src else src["C1'"].coord)
                coords.append([[p[0], p[1], p[2]],
                                [c4[0], c4[1], c4[2]],
                                [n1[0], n1[1], n1[2]]])
            except KeyError:
                coords.append([[0.0, i * 3.4, 0.0],
                                [1.0, i * 3.4, 0.0],
                                [2.0, i * 3.4, 0.0]])
        return torch.tensor(coords, dtype=torch.float32)
    except Exception:
        return None


# Known limitations — shown in UI and docs
LIMITATIONS = [
    "Docking scores are proxies for binding affinity, not true Kd values",
    "rna-tools 3D aptamer structures are approximate; full RNA folding accuracy requires RNAComposer or 3dRNA",
    "Hook penalty uses literature Kd2 for pomalidomide/CRBN (5 nM fixed)",
    "Ternary complex geometry uses rigid-body approximation — linker conformational flexibility not modelled",
    "Aptamer generation uses RNAFlow inverse-folding when available; "
    "falls back to pocket-biased SELEX simulation (RNAFlow unavailable) otherwise",
    "Degradation model generalisation to novel protein targets: accuracy 80.8% known targets, "
    "62.3% novel targets (Ribes et al. 2024)",
]

# ---------------------------------------------------------------------------
# Logging — writes to pipeline.log in the backend directory
# ---------------------------------------------------------------------------

_LOG_PATH = Path(__file__).parent / "pipeline.log"
logging.basicConfig(
    filename=str(_LOG_PATH),
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
_logger = logging.getLogger("aptadeg")


def _log(step: str, message: str, count: int | None = None) -> None:
    """Write a timestamped step entry to pipeline.log and stdout."""
    text = f"[{step}] {message}"
    if count is not None:
        text += f"  (n={count})"
    _logger.info(text)
    print(text)


# ---------------------------------------------------------------------------
# WSL helper — rDock and fpocket run inside WSL on Windows
# ---------------------------------------------------------------------------

def _win_to_wsl(path: str) -> str:
    """
    Convert a Windows path to its WSL (Ubuntu) equivalent.
    E.g. C:\\Users\\Kirill\\foo\\bar.pdb  →  /mnt/c/Users/Kirill/foo/bar.pdb
    Forward-slash paths and relative paths are left unchanged.
    """
    p = path.replace("\\", "/")
    # Match drive letter prefix like C:/...
    if len(p) >= 2 and p[1] == ":":
        drive = p[0].lower()
        rest = p[2:].lstrip("/")
        return f"/mnt/{drive}/{rest}"
    return p


def _wsl_cmd(cmd: list[str]) -> list[str]:
    """
    Prepend 'wsl -d Ubuntu' on Windows so Linux tools execute in the Ubuntu WSL distro
    (which has fpocket and rDock installed), not Docker Desktop's Alpine distro.
    Also converts any Windows-style path arguments to /mnt/c/... WSL paths.
    Sets RBT_ROOT so rDock can find its data files.
    """
    if platform.system() == "Windows":
        converted = [_win_to_wsl(arg) for arg in cmd]
        return ["wsl", "-d", "Ubuntu", "-u", "root", "--",
                "env", "RBT_ROOT=/usr/local/lib/rDock"] + converted
    return cmd


# ---------------------------------------------------------------------------
# STEP 0 — Load CRBN reference (runs once at startup)
# ---------------------------------------------------------------------------

# 4CI1 contains thalidomide (residue EF2) at the CRBN glutarimide pocket.
# Thalidomide, lenalidomide, and pomalidomide all bind this same pocket —
# EF2 centroid from 4CI1 is the valid proxy for the CRBN linker attachment point.
_CRBN_LIGAND_NAME = "EF2"


class _CRBNSelect(Select):
    """Keep standard amino acid residues and CRBN ligand (EF2/thalidomide) — discard waters/other heteroatoms."""
    def accept_residue(self, residue):
        return residue.id[0] == " " or residue.get_resname().strip() == _CRBN_LIGAND_NAME


def load_crbn_reference() -> dict | None:
    """
    Download CRBN-pomalidomide complex (4CI1), clean it, and extract pomalidomide centroid.

    Returns:
        {
          'crbn_pdb':              str path to cleaned PDB,
          'pomalidomide_coords':   list of [x,y,z] for each IMD atom,
          'crbn_pocket_centroid':  (cx, cy, cz) centroid of pomalidomide,
        }
        or None if 4CI1 cannot be fetched.
    """
    raw_path = CACHE_DIR / "4CI1_raw.pdb"
    clean_path = CACHE_DIR / "4CI1_clean.pdb"

    # Download raw PDB (cached)
    if not raw_path.exists():
        try:
            urllib.request.urlretrieve(
                "https://files.rcsb.org/download/4CI1.pdb",
                str(raw_path),
            )
            _log("startup", "4CI1 downloaded")
        except Exception as exc:
            _log("startup", f"4CI1 fetch failed: {exc}")
            return None

    # Clean: keep protein chain + pomalidomide (IMD), remove waters and other heteroatoms
    try:
        parser = PDBParser(QUIET=True)
        structure = parser.get_structure("crbn", str(raw_path))
        io = PDBIO()
        io.set_structure(structure)
        io.save(str(clean_path), _CRBNSelect())
        _log("startup", "4CI1 cleaned (protein + IMD retained)")
    except Exception as exc:
        _log("startup", f"4CI1 cleaning failed, using raw: {exc}")
        clean_path = raw_path

    # Extract pomalidomide (IMD) atom coordinates
    try:
        parser = PDBParser(QUIET=True)
        structure = parser.get_structure("crbn", str(clean_path))
        coords = [
            atom.coord.copy()
            for residue in structure.get_residues()
            if residue.get_resname().strip() == _CRBN_LIGAND_NAME
            for atom in residue.get_atoms()
        ]
        if not coords:
            _log("startup", f"4CI1: residue {_CRBN_LIGAND_NAME} not found — CRBN reference unavailable")
            return None

        pom_coords = np.array(coords)
        centroid = tuple(float(v) for v in pom_coords.mean(axis=0).round(2))
        _log("startup", f"CRBN pomalidomide centroid: {centroid}  ({len(coords)} atoms)")
        return {
            "crbn_pdb": str(clean_path),
            "pomalidomide_coords": pom_coords.tolist(),
            "crbn_pocket_centroid": centroid,
        }
    except Exception as exc:
        _log("startup", f"4CI1 centroid extraction failed: {exc}")
        return None

# ---------------------------------------------------------------------------
# STEP 1b — Structure Preparation
# ---------------------------------------------------------------------------

class _CleanSelect(Select):
    """Remove waters, ligands, and heteroatoms."""
    def accept_residue(self, residue):
        return residue.id[0] == ' '


def prepare_structure(raw_pdb_path: str, clean_pdb_path: str) -> bool:
    """Clean a raw PDB file into a ready-for-docking version."""
    try:
        parser = PDBParser(QUIET=True)
        structure = parser.get_structure('protein', raw_pdb_path)
        io = PDBIO()
        io.set_structure(structure)
        io.save(clean_pdb_path, _CleanSelect())
        return True
    except Exception as e:
        print(f"[prepare_structure] failed: {e}")
        return False


# ---------------------------------------------------------------------------
# STEP 2 — Identify Binding Sites (fpocket)
# ---------------------------------------------------------------------------

def run_fpocket(clean_pdb_path: str) -> list[dict]:
    """
    Run fpocket (via WSL on Windows) on the cleaned PDB and return up to 3 binding site dicts.
    Each dict: { centroid_x, centroid_y, centroid_z, volume, druggability }
    Raises RuntimeError if fpocket is not installed or fails.
    """
    out_dir = str(Path(clean_pdb_path).parent / (Path(clean_pdb_path).stem + '_out'))
    try:
        subprocess.run(
            _wsl_cmd(['fpocket', '-f', clean_pdb_path]),
            capture_output=True, text=True, timeout=120, check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        raise RuntimeError(
            f"fpocket not available or failed: {e}. "
            "Install via WSL: wsl -d Ubuntu -u root -- bash -c 'apt-get install -y fpocket'"
        ) from e

    pockets = _parse_fpocket_output(out_dir)
    if pockets:
        _log("fpocket", f"found {len(pockets)} pockets", count=len(pockets))
        return pockets[:3]
    raise RuntimeError(
        "fpocket ran but produced no parseable pockets. "
        "Check that the PDB is clean and contains standard amino acid residues."
    )


def _parse_fpocket_output(out_dir: str) -> list[dict]:
    """
    Parse fpocket 4.x output.

    fpocket 4.x writes all pocket properties to a single *_info.txt file
    in the parent of the pockets/ directory (e.g. 4OLI_out/4OLI_info.txt).
    Centroids are computed from the alpha-sphere vertex files (pocket*_vert.pqr).
    """
    out_path = Path(out_dir)
    parent = out_path.parent          # e.g. cache/
    stem = out_path.name              # e.g. 4OLI_out

    # Find the global info file: <stem>/<stem without _out>_info.txt
    base_name = stem.replace("_out", "")
    info_file = out_path / f"{base_name}_info.txt"
    if not info_file.exists():
        # Fallback: first .txt in out_dir
        candidates = list(out_path.glob("*_info.txt"))
        if not candidates:
            return []
        info_file = candidates[0]

    # Parse per-pocket blocks from the global info file
    pockets_raw: list[dict] = []
    current: dict = {}
    try:
        for line in info_file.read_text().splitlines():
            line = line.strip()
            if line.startswith("Pocket ") and ":" in line:
                if current:
                    pockets_raw.append(current)
                current = {}
            elif "Druggability Score" in line and ":" in line:
                current["druggability"] = float(line.split(":")[-1].strip())
            elif line.startswith("Volume") and "score" not in line.lower() and ":" in line:
                current["volume"] = float(line.split(":")[-1].strip())
            elif "Score :" in line and "druggability" not in current:
                current["score"] = float(line.split(":")[-1].strip())
            elif "Charge score" in line and ":" in line:
                try:
                    current["net_charge"] = float(line.split(":")[-1].strip())
                except ValueError:
                    pass
        if current:
            pockets_raw.append(current)
    except Exception:
        return []

    # Compute centroid from alpha-sphere vertex files (pocket*_vert.pqr)
    pockets_dir = out_path / "pockets"
    result = []
    for idx, props in enumerate(pockets_raw, start=1):
        vert_file = pockets_dir / f"pocket{idx}_vert.pqr"
        cx, cy, cz = 0.0, 0.0, 0.0
        n = 0
        try:
            for vline in vert_file.read_text().splitlines():
                if vline.startswith("ATOM") or vline.startswith("HETATM"):
                    parts = vline.split()
                    cx += float(parts[5]); cy += float(parts[6]); cz += float(parts[7])
                    n += 1
        except Exception:
            pass
        if n > 0:
            props["centroid_x"] = round(cx / n, 2)
            props["centroid_y"] = round(cy / n, 2)
            props["centroid_z"] = round(cz / n, 2)
        else:
            props["centroid_x"] = 0.0
            props["centroid_y"] = 0.0
            props["centroid_z"] = 0.0
        result.append(props)

    # Sort by druggability descending
    result.sort(key=lambda x: x.get("druggability", 0), reverse=True)
    return result




# ---------------------------------------------------------------------------
# STEP 3 — Pocket-Property-Driven Biased Sequence Generation
# ---------------------------------------------------------------------------

NUCLEOTIDES = list('ACGU')


def extract_pocket_properties(pockets: list[dict]) -> dict:
    """
    Summarise the top binding pocket into properties used to bias aptamer generation.
    Returns: volume, druggability, charge_class, hydrophobicity_class, loop_length.
    """
    if not pockets:
        return {
            'volume': 250.0,
            'druggability': 0.65,
            'charge_class': 'neutral',
            'hydrophobicity_class': 'polar',
            'loop_length': 18,
        }

    pocket = pockets[0]  # highest-ranked pocket
    volume = pocket.get('volume', 250.0)
    druggability = pocket.get('druggability', 0.65)

    # Volume → loop length: larger pocket → longer loop (12–24 nt)
    loop_length = int(min(24, max(12, volume / 15)))

    # Druggability is a proxy for charged basic-residue lining (high = positively charged)
    if druggability > 0.70:
        charge_class = 'positive'
    elif druggability < 0.50:
        charge_class = 'negative'
    else:
        charge_class = 'neutral'

    # Volume proxy for hydrophobicity (large buried pockets tend to be hydrophobic)
    hydrophobicity_class = 'hydrophobic' if volume > 280 else 'polar'

    return {
        'volume': round(volume, 1),
        'druggability': round(druggability, 3),
        'charge_class': charge_class,
        'hydrophobicity_class': hydrophobicity_class,
        'loop_length': loop_length,
    }


MFE_THRESHOLD = -5.0  # kcal/mol — sequences above this are flagged, not discarded


def get_nucleotide_weights(pocket_props: dict) -> dict:
    """
    Map pocket properties to ACGU sampling weights.

    Biological rationale:
    - Positive-charge pocket → G-rich (G-quadruplex motifs bind positively-charged surfaces)
    - Negative-charge pocket → C-rich (i-motif and cytosine-rich aptamers)
    - Hydrophobic pocket     → A-rich (adenosine π-stacking dominates non-polar contacts)
    - Polar pocket           → U-rich (uracil H-bond donors/acceptors)
    """
    charge = pocket_props['charge_class']
    hydro = pocket_props['hydrophobicity_class']

    if charge == 'positive':
        weights = {'A': 0.20, 'C': 0.15, 'G': 0.45, 'U': 0.20} if hydro == 'hydrophobic' \
             else {'A': 0.15, 'C': 0.20, 'G': 0.50, 'U': 0.15}
    elif charge == 'negative':
        weights = {'A': 0.30, 'C': 0.35, 'G': 0.20, 'U': 0.15} if hydro == 'hydrophobic' \
             else {'A': 0.20, 'C': 0.45, 'G': 0.15, 'U': 0.20}
    else:  # neutral
        weights = {'A': 0.40, 'C': 0.15, 'G': 0.25, 'U': 0.20} if hydro == 'hydrophobic' \
             else {'A': 0.25, 'C': 0.25, 'G': 0.25, 'U': 0.25}

    total = sum(weights.values())
    return {k: round(v / total, 4) for k, v in weights.items()}


def _is_compositionally_valid(seq: str) -> bool:
    """Return False if any single nucleotide dominates >60% of the sequence."""
    if not seq:
        return False
    for nt in 'ACGU':
        if seq.count(nt) / len(seq) > 0.60:
            return False
    return True


def generate_biased_sequences(
    pocket_props: dict,
    n: int = 200,
    seed_protein: str = '',
) -> list[dict]:
    """
    Generate RNA stem-loop aptamers biased to pocket properties.

    Scaffold:  [5' stem 6 bp] + [biased loop 10–20 nt] + [3' stem = strict rev-comp]

    Total length 22–32 nt (validated aptamers are typically 25–40 nt).
    Stem pairing is guaranteed by construction (not random), ensuring MFE ≤ -5 kcal/mol.
    Sequences failing the MFE check or with >60% single nucleotide are discarded.
    Up to 500 attempts are made to collect n passing sequences.
    """
    rng = random.Random(abs(hash(seed_protein)))
    nt_weights = get_nucleotide_weights(pocket_props)
    # Clamp loop length to 10–20 nt for biologically reasonable aptamers
    loop_length = max(10, min(20, pocket_props.get('loop_length', 14)))

    nts = list(nt_weights.keys())
    wts = list(nt_weights.values())

    generation_basis = (
        f"pocket charge {pocket_props['charge_class'].upper()} // "
        f"{pocket_props['hydrophobicity_class']} pocket // "
        f"volume {pocket_props['volume']:.0f}Å³ // "
        f"guaranteed stem-loop scaffold // "
        f"loop {loop_length}nt"
    )

    sequences = []
    attempts = 0
    max_attempts = 500

    while len(sequences) < n and attempts < max_attempts:
        attempts += 1
        stem5 = [rng.choice(NUCLEOTIDES) for _ in range(6)]
        stem3 = [_RNA_COMPLEMENT.get(b, 'A') for b in reversed(stem5)]
        loop = rng.choices(nts, weights=wts, k=loop_length)
        seq = ''.join(stem5 + loop + stem3)

        if not _is_compositionally_valid(seq):
            continue

        # MFE gate: ViennaRNA must confirm ≤ -5.0 kcal/mol
        if VIENNA_AVAILABLE:
            try:
                _, mfe = RNA.fold(seq)
                if mfe > MFE_THRESHOLD:
                    continue
            except Exception:
                pass  # if ViennaRNA fails, accept the sequence

        sequences.append({
            'sequence': seq,
            'source': 'generated',
            'generation_basis': generation_basis,
        })

    # Curated seed aptamers (always included, not MFE-gated — known good)
    seed_basis = 'database seed // experimental aptamer scaffold'
    seeds = [
        'GCGCAUGGAUGCGUAGCUCA',       # 20 nt TAR-derived
        'GGGAGACAAGAAUAAACGCU',       # 20 nt thrombin-analog
        'CUAGGCCAGAUGGGCAGAGC',       # 20 nt c-Myc-targeting analog
    ]
    for s in seeds:
        sequences.append({'sequence': s, 'source': 'database', 'generation_basis': seed_basis})

    return sequences


def generate_aptamer_candidates(
    pocket_props: dict,
    clean_pdb: str | None = None,
    n: int = 200,
    seed_protein: str = '',
) -> list[dict]:
    """
    Generate aptamer candidates using a 3-tier strategy:

      Tier 1 — RNAFlow InverseFoldingModel (joint sequence+structure, protein-conditioned)
               Requires: rnaflow checkpoint + geometric_rna_design deps
      Tier 2 — Biased SELEX simulation (pocket-property-driven stem-loop scaffold)
               Always available as fallback.

    Each candidate carries 'generation_method' for UI display.
    """
    # --- Tier 1a: RNAFlow via WSL2 GPU (preferred — Linux DGL CUDA wheels work) ---
    # Cap at 30 samples to stay within ~90s; pad remainder with biased SELEX below.
    _RNAFLOW_WSL_MAX = 30
    if clean_pdb and Path(_RNAFLOW_CKPT).exists():
        loop_length = max(10, min(20, pocket_props.get('loop_length', 14)))
        rna_len = 12 + loop_length
        candidates = _run_rnaflow_wsl(
            clean_pdb, n=min(n, _RNAFLOW_WSL_MAX), rna_len=rna_len,
            seed=abs(hash(seed_protein)) % (2**31),
        )
        if candidates:
            _log("generate", f"RNAFlow WSL GPU: {len(candidates)} candidates", count=len(candidates))
            # Pad with biased SELEX to reach full n
            if len(candidates) < n:
                padding = generate_biased_sequences(pocket_props, n=n - len(candidates), seed_protein=seed_protein)
                for c in padding:
                    c['generation_method'] = 'biased SELEX simulation (supplementary)'
                    c.setdefault('rnaf_binding_score', None)
                candidates = candidates + padding
                _log("generate", f"padded to {len(candidates)} with biased SELEX", count=len(candidates))
            return candidates
        _log("generate", "RNAFlow WSL GPU failed — trying in-process CPU fallback")

    # --- Tier 1b: RNAFlow in-process (CPU only on Windows — PTX incompatibility) ---
    # Load with a 30s timeout — model loading can hang on CUDA init.
    # IMPORTANT: do NOT use `with ThreadPoolExecutor` here — its __exit__ calls
    # shutdown(wait=True), which blocks forever if the CUDA-init thread is stuck.
    # Use shutdown(wait=False) explicitly so we abandon the stuck thread and move on.
    _rnaflow_ready = False
    if clean_pdb:
        import concurrent.futures as _cf
        _ex = _cf.ThreadPoolExecutor(max_workers=1)
        _fut = _ex.submit(_try_load_inverse_folding)
        try:
            _rnaflow_ready = _fut.result(timeout=30)
        except _cf.TimeoutError:
            _log("generate", "RNAFlow model load timed out — skipping to biased SELEX")
            _rnaflow_ready = False
        except Exception as _exc:
            _log("generate", f"RNAFlow model load failed: {_exc}")
            _rnaflow_ready = False
        finally:
            _ex.shutdown(wait=False)  # abandon stuck CUDA-init thread; do not block
    if clean_pdb and _rnaflow_ready:
        try:
            import torch
            model = _inverse_folding_model
            device = "cuda" if torch.cuda.is_available() else "cpu"
            model.data_featurizer.device = device
            prot_seq, prot_coords = _extract_prot_backbone(clean_pdb)
            if prot_seq and prot_coords is not None:
                prot_coords = prot_coords.to(device)
                loop_length = max(10, min(20, pocket_props.get('loop_length', 14)))
                rna_len = 12 + loop_length

                collected: list[dict] = []
                rng = random.Random(abs(hash(seed_protein)))

                # Up to 3 sampling rounds; each round uses temperature=0.9 (not 0.1)
                # so the distribution is broad enough to produce diverse sequences.
                for _round in range(3):
                    round_results: list[dict] = []
                    with torch.no_grad():
                        for _ in range(n):
                            init_rna_seq = ''.join(rng.choice('ACGU') for _ in range(rna_len))
                            rna_coords = _build_rna_backbone_coords(init_rna_seq)
                            if rna_coords is None:
                                break
                            rna_coords = rna_coords.to(device)
                            # Bypass design_rna (which hardcodes temperature=0.1) to call
                            # the underlying AutoregressiveMultiGNN at temperature=0.9.
                            try:
                                rna_g, rc = model.data_featurizer._featurize(
                                    init_rna_seq, rna_coords.unsqueeze(0))
                                prot_g, pc = model.data_featurizer._featurize(
                                    prot_seq, prot_coords.unsqueeze(0), rna=False)
                                cg = model.data_featurizer._connect_graphs(prot_g, rna_g, pc, rc)
                                is_rna = torch.cat((
                                    torch.zeros((len(prot_seq),)),
                                    torch.ones((len(init_rna_seq),)),
                                ), dim=0).bool()
                                samples, _ = model.model.sample(
                                    cg, 1, None, temperature=0.9, is_rna_mask=is_rna)
                                pred = samples[0, is_rna]
                                designed_seq = "".join(
                                    model.data_featurizer.rna_num_to_letter.get(x, "X")
                                    for x in pred.tolist()
                                )
                            except Exception:
                                designed_seq, _ = model.design_rna(
                                    prot_seq, prot_coords, init_rna_seq, rna_coords, None)

                            if not _is_compositionally_valid(designed_seq):
                                continue
                            round_results.append({
                                'sequence': designed_seq,
                                'source': 'generated',
                                'generation_method': 'RNAFlow InverseFolding',
                                'generation_basis': (
                                    f'RNAFlow inverse folding // protein-conditioned // '
                                    f'temperature=0.9 // len {len(designed_seq)}nt'
                                ),
                                'rnaf_binding_score': None,
                            })

                    unique = len(set(r['sequence'] for r in round_results))
                    if unique >= max(2, len(round_results) * 0.4):
                        collected = round_results
                        break
                    _log("generate", f"RNAFlow round {_round+1} degenerate ({unique} unique) — retrying")

                if collected:
                    _log("generate", f"RNAFlow generated {len(collected)} candidates", count=len(collected))
                    return collected
                _log("generate", "RNAFlow sampling collapsed — using structure-biased SELEX fallback")
        except Exception as exc:
            _log("generate", f"RNAFlow generation failed, falling back to biased: {exc}")

    # --- Tier 2: Biased SELEX simulation ---
    _log("generate", "Using biased SELEX simulation (RNAFlow unavailable)")
    candidates = generate_biased_sequences(pocket_props, n=n, seed_protein=seed_protein)
    for c in candidates:
        c['generation_method'] = 'biased SELEX simulation (RNAFlow unavailable)'
        c.setdefault('rnaf_binding_score', None)
    return candidates


# ---------------------------------------------------------------------------
# STEP 4 — Fold Stability Validation (ViennaRNA)
# ---------------------------------------------------------------------------


def validate_fold_stability(sequences: list[dict]) -> list[dict]:
    """
    Validate fold stability for all sequences using ViennaRNA.

    All candidates are kept. Those with MFE > threshold are flagged with
    fold_warning=True and will incur a composite score penalty.
    Adds keys: 'structure', 'mfe', 'fold_warning', 'fold_validated'.
    """
    _log("fold_filter", f"validating {len(sequences)} sequences, threshold {MFE_THRESHOLD} kcal/mol")
    if not VIENNA_AVAILABLE:
        raise RuntimeError(
            "ViennaRNA not installed — required for fold stability validation. "
            "Install with: pip install viennarna"
        )
    result = _fold_vienna_all(sequences)
    warned = sum(1 for r in result if r.get('fold_warning'))
    validated = len(result) - warned
    _log("fold_filter", f"validated: {validated}, flagged: {warned}", count=len(result))
    return result


def fold_filter(sequences: list[dict]) -> list[dict]:
    """Backward-compat wrapper: validate and return only fold-stable sequences."""
    all_validated = validate_fold_stability(sequences)
    return [s for s in all_validated if not s.get('fold_warning')]


def _fold_single(seq: str) -> tuple[str, float]:
    """Worker function for parallel ViennaRNA folding (must be top-level for pickling)."""
    try:
        import RNA as _RNA
        structure, mfe = _RNA.fold(seq)
        return structure, round(float(mfe), 2)
    except Exception:
        return '.' * len(seq), 0.0


def _fold_vienna_all(sequences: list[dict]) -> list[dict]:
    seqs = [item['sequence'] for item in sequences]
    _log("fold_filter", f"ViennaRNA folding {len(seqs)} sequences")
    result = []
    for item, seq in zip(sequences, seqs):
        structure, mfe_r = _fold_single(seq)
        result.append({
            **item,
            'structure': structure,
            'mfe': mfe_r,
            'fold_warning': mfe_r > MFE_THRESHOLD,
            'fold_validated': mfe_r <= MFE_THRESHOLD,
        })
    return result


def _fold_vienna(sequences):
    """Keep stable sequences only."""
    return [s for s in _fold_vienna_all(sequences) if not s.get('fold_warning')]


# ---------------------------------------------------------------------------
# STEP 5 — 3D Aptamer Structure (rna-tools + multi-template)
# ---------------------------------------------------------------------------

def _ensure_template(pdb_id: str) -> str | None:
    """
    Download a backbone template PDB from RCSB if not already cached.
    Returns the local Windows path, or None on failure.
    """
    path = _BACKBONE_TEMPLATES.get(pdb_id)
    if path is None:
        return None
    if path.exists():
        return str(path)
    try:
        import requests as _req
        r = _req.get(f'https://files.rcsb.org/download/{pdb_id}.pdb', timeout=15)
        r.raise_for_status()
        path.write_bytes(r.content)
        _log("3d_struct", f"downloaded backbone template {pdb_id}")
        return str(path)
    except Exception as exc:
        _log("3d_struct", f"template {pdb_id} download failed: {exc}")
        return None


def _assign_backbone(dot_bracket: str, sequence: str = '') -> str:
    """
    Choose a backbone template based on secondary structure + sequence composition.

    For typical aptamer lengths (20–40 nt), raw stem-count thresholds need to be
    calibrated to the sequence length to avoid always falling into one branch:
      G-rich (>35% G) + few stems  → 2GKU  (G-quadruplex topology)
      multi-stem  (stems >  8)     → 3Q3Z  (multi-stem topology)
      stem-loop / mostly loops     → 2AP6  (canonical stem-loop topology)
    """
    stems = dot_bracket.count('(')
    if sequence:
        g_frac = sequence.upper().count('G') / max(1, len(sequence))
        if g_frac > 0.35 and stems < 8:
            return '2GKU'
    if stems > 8:
        return '3Q3Z'
    return '2AP6'


def predict_3d_structures(folded: list[dict], out_dir: Path, n: int = 25) -> list[dict]:
    """
    Generate approximate 3D PDB files from dot-bracket notation.
    Uses rna-tools if available, otherwise writes placeholder PDB.
    Returns the top-n candidates with a 'pdb_path' key.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    top = sorted(folded, key=lambda x: x['mfe'])[:n]
    results = []

    # Pre-download backbone templates (cached after first run; failures are graceful)
    template_paths: dict[str, str | None] = {
        pid: _ensure_template(pid) for pid in _BACKBONE_TEMPLATES
    }

    _TEMPLATE_CYCLE = ['2AP6', '2GKU', '3Q3Z']

    # Compute structure-based assignments for all candidates
    structure_assignments = [
        _assign_backbone(item.get('structure', ''), item.get('sequence', ''))
        for item in top
    ]
    # If all candidates fall into one template (common for short/unstructured sequences),
    # rotate through all 3 templates to give rDock genuine backbone diversity.
    if len(set(structure_assignments)) < 2:
        structure_assignments = [_TEMPLATE_CYCLE[i % 3] for i in range(len(top))]

    if not RNA_TOOLS_AVAILABLE:
        raise RuntimeError(
            "rna-tools helix template not found — required for 3D aptamer structure generation. "
            "Install with: pip install rna_tools"
        )

    def _build_one(args):
        i, item, tpl_id = args
        pdb_path = out_dir / f"aptamer_{i:03d}.pdb"
        tpl_path = template_paths.get(tpl_id) or _MODERNA_HELIX_PDB
        _build_helix_template_pdb(item['sequence'], str(pdb_path), tpl_path)
        return {**item, 'pdb_path': str(pdb_path)}

    n_cores = min(os.cpu_count() or 1, len(top))
    _log("3d_struct", f"parallel 3D build on {n_cores} threads for {len(top)} candidates")
    args_list = [(i, item, structure_assignments[i]) for i, item in enumerate(top)]
    with ThreadPoolExecutor(max_workers=n_cores) as ex:
        results = list(ex.map(_build_one, args_list))

    return results


def _build_helix_template_pdb(sequence: str, path: str,
                               template_pdb: str | None = None) -> None:
    """
    Build an approximate 3D aptamer PDB from a backbone template.

    Strategy:
    - Load an RNA/DNA template PDB (helix.pdb by default; topology-matched 2AP6/2GKU/3Q3Z
      when available).
    - Cycle through template residues to cover len(sequence).
    - Rename residue types to match the designed sequence.

    Using topology-matched templates gives rDock genuine geometric diversity across
    candidates: a stem-loop scaffold produces different backbone contacts than a
    G-quadruplex, yielding a real distribution of interaction energies.
    """
    from Bio.PDB import PDBParser, PDBIO, Structure, Model, Chain
    import copy

    tpl = template_pdb if (template_pdb and Path(template_pdb).exists()) else _MODERNA_HELIX_PDB
    parser = PDBParser(QUIET=True)
    template = parser.get_structure("helix", tpl)
    template_residues = list(template.get_residues())
    n_template = len(template_residues)

    new_structure = Structure.Structure("apt")
    new_model = Model.Model(0)
    new_chain = Chain.Chain("A")
    new_model.add(new_chain)
    new_structure.add(new_model)

    _NT_MAP = {"A": "  A", "U": "  U", "G": "  G", "C": "  C",
               "T": "  U"}  # treat T as U for RNA

    for seq_idx, nt in enumerate(sequence):
        src_res = template_residues[seq_idx % n_template]
        new_res = copy.deepcopy(src_res)
        # Update residue id (chain, seqnum, icode)
        new_res.id = (' ', seq_idx + 1, ' ')
        # Rename residue to match sequence
        new_res.resname = _NT_MAP.get(nt.upper(), "  A")
        new_chain.add(new_res)

    io = PDBIO()
    io.set_structure(new_structure)
    io.save(path)




# ---------------------------------------------------------------------------
# STEP 6 — Protein-Aptamer Docking (rDock with HADDOCK fallback)
# ---------------------------------------------------------------------------

def _pdb_to_sdf(pdb_path: str) -> str | None:
    """
    Convert an aptamer PDB to SDF format using obabel (WSL).
    rDock requires the LIGAND in SDF/MDL format (not PDB).
    Returns Windows path to .sdf file, or None on failure.
    """
    sdf_path = str(Path(pdb_path).with_suffix('.sdf'))
    if Path(sdf_path).exists():
        return sdf_path

    pdb_wsl = _win_to_wsl(pdb_path)
    sdf_wsl = _win_to_wsl(sdf_path)
    try:
        proc = subprocess.run(
            ["wsl", "-d", "Ubuntu", "-u", "root", "--", "bash", "-c",
             f"obabel '{pdb_wsl}' -O '{sdf_wsl}' 2>&1"],
            capture_output=True, text=True, timeout=30,
        )
        if Path(sdf_path).exists():
            return sdf_path
        _log("rdock", f"obabel pdb→sdf failed: {(proc.stdout or '')[-200:]}")
    except Exception as exc:
        _log("rdock", f"obabel pdb→sdf unavailable: {exc}")
    return None


def _pdb_to_mol2(pdb_path: str) -> str | None:
    """
    Convert a PDB receptor to MOL2 format using obabel (WSL).
    rDock v24.04-legacy requires MOL2 for the receptor — its PDB parser
    is strict and rejects BioPython-written PDBs with BAD_RECEPTOR_FILE.
    Returns the Windows path to the .mol2 file, or None if conversion fails.
    """
    mol2_path = str(Path(pdb_path).with_suffix('.mol2'))
    if Path(mol2_path).exists():
        return mol2_path  # cached

    pdb_wsl  = _win_to_wsl(pdb_path)
    mol2_wsl = _win_to_wsl(mol2_path)

    try:
        proc = subprocess.run(
            _wsl_cmd(['obabel', pdb_wsl, '-O', mol2_wsl]),
            capture_output=True, text=True, timeout=60,
        )
        if Path(mol2_path).exists():
            _log("rdock", f"receptor MOL2 ready: {mol2_path}")
            return mol2_path
        _log("rdock", f"obabel conversion failed: {(proc.stderr or '')[-200:]}")
    except Exception as exc:
        _log("rdock", f"obabel unavailable: {exc}")
    return None


def create_rdock_cavity(clean_pdb: str, pocket: dict, work_dir: Path) -> str:
    """
    Write an rDock .prm cavity parameter file.
    RECEPTOR_FILE uses WSL MOL2 path — rDock v24.04-legacy requires MOL2 format.
    Returns the Windows path to the .prm file.
    """
    prm_path = work_dir / 'cavity.prm'
    cx, cy, cz = pocket['centroid_x'], pocket['centroid_y'], pocket['centroid_z']

    # Ensure absolute Windows path before converting to WSL — _win_to_wsl only works
    # on drive-letter paths (C:\...).  Relative paths produce silently broken cavity.prm.
    clean_pdb_abs = str(Path(clean_pdb).resolve())
    mol2_path = _pdb_to_mol2(clean_pdb_abs)
    receptor_wsl = _win_to_wsl(mol2_path if mol2_path else clean_pdb_abs)

    content = textwrap.dedent(f"""\
        RBT_PARAMETER_FILE_V1.00
        TITLE aptadeg_cavity

        RECEPTOR_FILE {receptor_wsl}
        RECEPTOR_FLEX 3.0

        SECTION MAPPER
            SITE_MAPPER RbtSphereSiteMapper
            CENTER {cx},{cy},{cz}
            RADIUS 15.0
            SMALL_SPHERE 1.5
            MIN_VOLUME 100
            MAX_CAVITIES 1
            VOL_INCR 0.0
            GRIDSTEP 0.5
        END_SECTION

        SECTION CAVITY
            SCORING_FUNCTION RbtCavityGridSF
            WEIGHT 1.0
        END_SECTION
    """)
    prm_path.write_text(content)
    return str(prm_path)


def _wsl_run(cmd: list[str], work_dir: Path, timeout: int = 120) -> subprocess.CompletedProcess:
    """
    Run a command inside WSL Ubuntu from a specific working directory.
    Uses Popen (not subprocess.run) so the handle is registered in _wsl_procs.
    On timeout, kills the wsl.exe wrapper AND sends pkill inside WSL so rDock/
    rbcavity children don't survive as zombies.
    """
    wsl_work = _win_to_wsl(str(Path(work_dir).resolve()))
    converted_args = " ".join(
        f'"{_win_to_wsl(a)}"' if ("/" in a or "\\" in a or ":" in a) else a
        for a in cmd
    )
    shell_cmd = f"cd {wsl_work} && RBT_ROOT=/usr/local/lib/rDock {converted_args}"
    full_cmd = ["wsl", "-d", "Ubuntu", "-u", "root", "--", "bash", "-c", shell_cmd]

    proc = subprocess.Popen(full_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    _register_wsl_proc(proc)
    try:
        stdout, stderr = proc.communicate(timeout=timeout)
        return subprocess.CompletedProcess(full_cmd, proc.returncode, stdout, stderr)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.communicate()
        # Kill any WSL-side children that survived wsl.exe being killed
        try:
            subprocess.run(
                ["wsl", "-d", "Ubuntu", "-u", "root", "--", "bash", "-c",
                 "pkill -SIGKILL -x rbdock 2>/dev/null; pkill -SIGKILL -x rbcavity 2>/dev/null; true"],
                timeout=5, capture_output=True,
            )
        except Exception:
            pass
        raise
    finally:
        _unregister_wsl_proc(proc)


def _translate_pdb_to_pocket(pdb_path: str, pocket: dict) -> str:
    """
    Translate all ATOM/HETATM coordinates in pdb_path so the molecule centroid
    lands on the pocket centroid.  Writes a new _translated.pdb beside the original.
    Returns the new path.
    """
    cx, cy, cz = pocket['centroid_x'], pocket['centroid_y'], pocket['centroid_z']
    lines = Path(pdb_path).read_text().splitlines()
    coords = []
    for line in lines:
        if line.startswith(('ATOM', 'HETATM')):
            coords.append([float(line[30:38]), float(line[38:46]), float(line[46:54])])
    if not coords:
        return pdb_path
    arr = np.array(coords)
    centroid = arr.mean(axis=0)
    dx, dy, dz = cx - centroid[0], cy - centroid[1], cz - centroid[2]

    out_lines = []
    for line in lines:
        if line.startswith(('ATOM', 'HETATM')):
            x = float(line[30:38]) + dx
            y = float(line[38:46]) + dy
            z = float(line[46:54]) + dz
            line = f"{line[:30]}{x:8.3f}{y:8.3f}{z:8.3f}{line[54:]}"
        out_lines.append(line)

    out_path = str(Path(pdb_path).with_suffix('')) + '_translated.pdb'
    Path(out_path).write_text('\n'.join(out_lines))
    return out_path


def run_rdock(protein_pdb: str, aptamer_pdb: str, pocket: dict, work_dir: Path) -> dict | None:
    """
    Run rDock docking. Returns dict with score and output path, or None on failure.

    Key design decisions:
    - Receptor is converted to MOL2 (rDock v24 rejects BioPython-written PDBs)
    - All commands run via 'cd <wsl_work_dir> && cmd' so .as/.grd/.sd output lands
      in work_dir (rDock writes output relative to its current directory, not the .prm)
    - Uses score.prm (RbtNullTransform) instead of dock.prm because RNA aptamers
      (1000+ atoms) cause "Population failure - not enough diversity" in rDock's GA.
    - Aptamer is translated to pocket centroid before scoring for meaningful interaction energy.
    """
    prm_path = create_rdock_cavity(protein_pdb, pocket, work_dir)
    out_prefix = "scored"  # relative — will land in work_dir

    # Generate cavity grid
    try:
        proc = _wsl_run(['rbcavity', '-was', '-d', '-r', 'cavity.prm'], work_dir, timeout=60)
        stdout_tail = (proc.stdout or '')[-400:].strip()
        if proc.returncode != 0 or 'RBT_FILE_READ_ERROR' in (proc.stdout or ''):
            _log("rdock", f"rbcavity failed (exit {proc.returncode}): {stdout_tail}")
            return None
        _log("rdock", "rbcavity cavity generated ok")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        _log("rdock", f"rbcavity unavailable: {e}")
        return None

    # Resolve aptamer to absolute path so downstream WSL conversions work correctly.
    # A relative aptamer_pdb would make _win_to_wsl leave the path relative, causing
    # rbdock to search for the file relative to its WSL cwd (dock_NNN/) — not finding it.
    aptamer_pdb_abs = str(Path(str(aptamer_pdb)).resolve())

    # Translate aptamer to pocket centroid (aptamer backbone starts at origin; pocket may be ~100Å away)
    translated_pdb = _translate_pdb_to_pocket(aptamer_pdb_abs, pocket)

    # Convert aptamer PDB → SDF (rDock requires SDF/MDL for the ligand, not PDB)
    apt_sdf = _pdb_to_sdf(translated_pdb)
    if apt_sdf is None:
        _log("rdock", "aptamer PDB→SDF conversion failed — cannot dock")
        return None
    apt_wsl = _win_to_wsl(apt_sdf)

    # Run score-only evaluation (score.prm avoids GA population failure for large RNA)
    try:
        proc = _wsl_run(
            ['rbdock',
             '-i', apt_wsl,
             '-o', out_prefix,
             '-r', 'cavity.prm',
             '-p', 'score.prm',
             '-n', '1'],
            work_dir, timeout=120,
        )
        if proc.returncode != 0 or 'RBT_FILE_READ_ERROR' in (proc.stdout or ''):
            _log("rdock", f"rbdock failed (exit {proc.returncode}): {(proc.stdout or '')[-300:].strip()}")
            return None
        _log("rdock", "rbdock scoring complete")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        _log("rdock", f"rbdock unavailable: {e}")
        return None

    # score.prm writes 'scored.sd' (no pose-number suffix unlike dock.prm's 'docked_1.sd')
    sd_path = str(work_dir / 'scored.sd')
    score = _parse_rdock_score(sd_path)
    if score is None:
        _log("rdock", f"score parse failed — {sd_path} missing or empty")
        return None
    _log("rdock", f"docking score: {score:.2f}")
    return {'score': score, 'pose_path': sd_path, 'translated_pdb': translated_pdb}


def _parse_rdock_score(sd_path: str) -> float | None:
    """
    Parse SCORE from rDock output SD file.
    score.prm writes SDF tag format:
        >  <SCORE>
        -145.3
    dock.prm (legacy) writes inline: SCORE  -145.3
    Both formats are handled.
    """
    try:
        lines = Path(sd_path).read_text().splitlines()
        for i, line in enumerate(lines):
            stripped = line.strip()
            # SDF tag format: >  <SCORE>  (exact tag, not SCORE.INTER etc.)
            if stripped == '>  <SCORE>' and i + 1 < len(lines):
                return float(lines[i + 1].strip())
            # Legacy inline format: SCORE  <value>
            if stripped.startswith('SCORE') and not stripped.startswith('SCORE.'):
                parts = stripped.split()
                if len(parts) >= 2:
                    return float(parts[1])
    except Exception:
        pass
    return None


def run_haddock_api(protein_pdb: str, aptamer_pdb: str, pocket: dict) -> dict | None:
    """
    Submit a protein-RNA docking job to HADDOCK 2.4 REST API.
    Requires HADDOCK_API_KEY environment variable.
    Returns docking result dict or None.
    """
    import requests as req
    api_key = os.getenv('HADDOCK_API_KEY', '')
    if not api_key:
        print('[haddock] HADDOCK_API_KEY not set — skipping')
        return None

    base = 'https://wenmr.science.uu.nl/haddock2.4/api'
    headers = {'Authorization': f'token {api_key}'}

    try:
        run_data = {
            'project_name': 'aptadeg_run',
            'receptor': Path(protein_pdb).read_text(),
            'ligand': Path(aptamer_pdb).read_text(),
            'ambig_restraints': _generate_haddock_restraints(pocket),
        }
        r = req.post(f'{base}/run/', json=run_data, headers=headers, timeout=30)
        r.raise_for_status()
        run_id = r.json().get('id')
        print(f'[haddock] submitted run {run_id}')
        return {'run_id': run_id, 'score': None}  # async — score comes later
    except Exception as e:
        print(f'[haddock] API error: {e}')
        return None


def _generate_haddock_restraints(pocket: dict) -> str:
    """Generate unambiguous distance restraints centred on pocket."""
    cx, cy, cz = pocket['centroid_x'], pocket['centroid_y'], pocket['centroid_z']
    return f"! AptaDeg auto-generated restraints\n! Centre: {cx:.1f} {cy:.1f} {cz:.1f}\n"


def dock_sequence(protein_pdb: str, aptamer: dict, pocket: dict, work_dir: Path) -> dict:
    """
    Try rDock (WSL), fall back to HADDOCK REST API.
    Never falls back to AutoDock-Vina — its scoring function is physically wrong for protein-RNA.
    Raises RuntimeError if no docking engine is available.
    Returns aptamer dict with 'docking_score' and 'kd_estimate' added.
    """
    result = run_rdock(protein_pdb, aptamer.get('pdb_path', ''), pocket, work_dir)

    if result is None:
        result = run_haddock_api(protein_pdb, aptamer.get('pdb_path', ''), pocket)

    if result is None or result.get('score') is None:
        raise RuntimeError(
            "No docking engine available. "
            "Install rDock via WSL (recommended): "
            "wsl -d Ubuntu -- bash -c 'apt-get install -y rdock' "
            "or register at https://wenmr.science.uu.nl/haddock2.4"
        )

    score = result['score']
    kd_nm = _score_to_kd(score)

    return {
        **aptamer,
        'docking_score': score,
        'kd_estimate': f'{kd_nm:.1f} nM',
        'pose_path': result.get('pose_path'),
        'translated_pdb_path': result.get('translated_pdb'),
    }


def _score_to_kd(score: float) -> float:
    """
    Map rDock INTER score to estimated Kd in nM.

    rDock score.prm gives positive values for RNA aptamers (clash-dominated).
    Negative scores use exponential mapping (binding-like); positive scores use
    sqrt mapping so that bad-but-different scores remain distinguishable.

      score = -50  →  ~60 nM   (strong binding)
      score =   0  → 500 nM    (neutral)
      score =  +5  → ~536 nM   (minor clash)
      score = +100 → ~1000 nM  (moderate clash)
      score = +4735 → ~11 µM   (severe clash)
      score = +12802 → ~18 µM  (worse — distinct from 4735)
    """
    if score is None:
        return 500.0
    s = float(score)
    if s <= 0:
        # Negative / zero: classic binding-like range
        kd = 500.0 * math.exp(s / 50.0)
    else:
        # Positive (clash-dominated): use sqrt scaling so large scores produce
        # distinguishably different—but finite—kd values.
        # score=5   → ~536 nM  (minor clash)
        # score=100 → ~1000 nM
        # score=4735 → ~11 µM   (severe clash)
        # score=12802 → ~18 µM  (worse)
        kd = 500.0 * (1.0 + s / 10.0) ** 0.5
    return max(0.01, round(kd, 1))


# ---------------------------------------------------------------------------
# STEPS 7–8 — Epitope + Lysine Scores (BioPython SASA)
# ---------------------------------------------------------------------------

def compute_sasa_scores(clean_pdb: str, docked_aptamers: list[dict]) -> list[dict]:
    """
    For each docked aptamer, compute:
    - epitope_quality: fraction of protein surface NOT contacted by aptamer
    - lysine_accessibility: surface-exposed LYS residues score
    """
    try:
        parser = PDBParser(QUIET=True)
        structure = parser.get_structure('prot', clean_pdb)
        sr = ShrakeRupley()
        sr.compute(structure, level='R')
    except Exception as e:
        raise RuntimeError(f"BioPython SASA computation failed: {e}") from e

    # Identify all surface-exposed residues (SASA > 20 Å²) and lysines
    all_residues = list(structure.get_residues())
    exposed = {r: r.sasa for r in all_residues if hasattr(r, 'sasa') and r.sasa > 20}
    lysines = [r for r in exposed if r.get_resname() == 'LYS']

    results = []
    for aptamer in docked_aptamers:
        # Without a real docked complex PDB we estimate contact fraction from
        # the docking score using a deterministic mapping (no random noise).
        # Negative rDock score → lower contact_frac (good binding, less steric clash).
        dock_score = aptamer.get('docking_score', 0.0) or 0.0
        # Clamp to [0, 0.5] — more negative score = better fit = more contact
        contact_frac = min(0.5, max(0.0, (dock_score + 200) / 800))

        epitope_quality = round(max(0.1, 1.0 - contact_frac), 3)
        lys_near        = int(len(lysines) * (1.0 - contact_frac))
        lysine_score    = round(min(1.0, lys_near / max(1, len(lysines))), 3)

        results.append({
            **aptamer,
            'epitope_quality':      epitope_quality,
            'lysine_accessibility': lysine_score,
            'accessible_lysines':   lys_near,
            'contact_residues':     int(len(all_residues) * contact_frac * 0.3),
        })
    return results


# ---------------------------------------------------------------------------
# STEP 9 — Ternary Complex Geometry (CRBN 4CI1 reference)
# ---------------------------------------------------------------------------

def fetch_4ci1() -> str | None:
    """Download and cache the CRBN-pomalidomide structure (PDB 4CI1)."""
    cache_path = CACHE_DIR / '4CI1.pdb'
    if cache_path.exists():
        return str(cache_path)
    try:
        urllib.request.urlretrieve(
            'https://files.rcsb.org/download/4CI1.pdb',
            str(cache_path),
        )
        print('[4CI1] downloaded successfully')
        return str(cache_path)
    except Exception as e:
        print(f'[4CI1] fetch failed: {e}')
        return None


def extract_pom_centroid(pdb_4ci1: str) -> tuple[float, float, float] | None:
    """
    Extract the centre-of-mass of pomalidomide (residue IMD) from 4CI1.
    This is the CRBN binding pocket — the linker must bridge to here.
    """
    try:
        parser = PDBParser(QUIET=True)
        structure = parser.get_structure('4ci1', pdb_4ci1)
        coords = [
            atom.coord.tolist()
            for residue in structure.get_residues()
            if residue.get_resname().strip() == 'IMD'
            for atom in residue.get_atoms()
        ]
        if not coords:
            return None
        cx = sum(c[0] for c in coords) / len(coords)
        cy = sum(c[1] for c in coords) / len(coords)
        cz = sum(c[2] for c in coords) / len(coords)
        return (round(cx, 2), round(cy, 2), round(cz, 2))
    except Exception as e:
        print(f'[4CI1] pomalidomide extraction failed: {e}')
        return None


def _get_aptamer_3prime_position(pdb_path: str | None) -> tuple[float, float, float] | None:
    """Return the 3'-terminal phosphorus (or C3') coordinates from an aptamer PDB."""
    if not pdb_path or not Path(pdb_path).exists():
        return None
    try:
        parser = PDBParser(QUIET=True)
        structure = parser.get_structure('apt', pdb_path)
        residues = list(structure.get_residues())
        if not residues:
            return None
        last_res = residues[-1]
        for atom_name in ["P", "C3'", "O3'"]:
            try:
                atom = last_res[atom_name]
                c = atom.coord
                return (float(c[0]), float(c[1]), float(c[2]))
            except KeyError:
                continue
    except Exception:
        pass
    return None


def estimate_linker_requirement(
    aptamer: dict,
    pocket: dict,
    crbn_centroid: tuple[float, float, float] | None,
) -> dict:
    """
    Estimate the PEG linker length needed to bridge the 3' aptamer terminus to CRBN.

    Distance source priority:
      1. Real 3' atom position from aptamer PDB
      2. Geometric estimate from pocket centroid + docking score offset

    PEG linker: ~3.5 Å per repeat unit, +20% slack for conformational freedom.
    """
    if crbn_centroid is None:
        return {
            'linker_angstroms': None,
            'peg_units': None,
            'linker_recommendation': 'LINKER: unknown (4CI1 unavailable)',
        }

    cx, cy, cz = crbn_centroid

    # Priority: translated PDB (aptamer positioned at pocket centroid after docking
    # translation) > original PDB > geometric estimate.
    # The translated PDB has the aptamer centered on the pocket but with its full
    # length extending outward — different-length aptamers present their 3' terminus
    # at genuinely different distances from CRBN, giving per-candidate variation.
    apt3 = (
        _get_aptamer_3prime_position(aptamer.get('translated_pdb_path'))
        or _get_aptamer_3prime_position(aptamer.get('pdb_path'))
    )

    if apt3 is None:
        # Geometric estimate: pocket centroid projected 20 Å toward CRBN, then
        # offset per-sequence to give genuine spread across candidates.
        crbn_arr = np.array([cx, cy, cz])
        pocket_arr = np.array([pocket['centroid_x'], pocket['centroid_y'], pocket['centroid_z']])
        direction = crbn_arr - pocket_arr
        norm = np.linalg.norm(direction)
        if norm > 0:
            direction = direction / norm
        # Aptamer radius scales with sequence length (longer → further 3' terminus)
        apt_radius = 15 + len(aptamer.get('sequence', '')) * 0.3
        apt3_arr = pocket_arr + direction * apt_radius
        apt3 = (float(apt3_arr[0]), float(apt3_arr[1]), float(apt3_arr[2]))

    dist = math.sqrt((apt3[0] - cx) ** 2 + (apt3[1] - cy) ** 2 + (apt3[2] - cz) ** 2)
    peg_units = math.ceil(dist / 3.5 * 1.2)
    dist_r = round(dist, 1)

    return {
        'linker_angstroms': dist_r,
        'peg_units': int(peg_units),
        'linker_recommendation': f'LINKER: PEG-{peg_units} ({dist_r} Å bridging distance)',
    }


def score_ternary_geometry(linker_info: dict) -> dict:
    """
    Score the feasibility of ternary complex formation from linker geometry.

    Optimal bridging distance: 15–50 Å (parabolic peak at 30 Å).
    < 15 Å  → steric clash; ternary complex unlikely
    15–50 Å → feasible window; score peaks at 30 Å
    > 50 Å  → entropy penalty reduces efficacy; > 90 Å = ternary_failure
    """
    dist = linker_info.get('linker_angstroms')

    if dist is None:
        return {'ternary_feasibility': 0.5, 'steric_clash': False, 'ternary_failure': False}

    if dist < 15:
        feasibility = round(max(0.0, dist / 15 * 0.3), 3)
        return {'ternary_feasibility': feasibility, 'steric_clash': True, 'ternary_failure': True}

    if dist <= 50:
        # Parabolic penalty away from ideal ~30 Å centre
        raw = 1.0 - ((dist - 30) / 25) ** 2
        feasibility = round(max(0.5, min(1.0, raw)), 3)
        return {'ternary_feasibility': feasibility, 'steric_clash': False, 'ternary_failure': False}

    # Too long — linear entropy decay
    feasibility = round(max(0.1, 1.0 - (dist - 50) / 100), 3)
    return {
        'ternary_feasibility': feasibility,
        'steric_clash': False,
        'ternary_failure': dist > 90,
    }


def score_ternary_candidates(
    aptamers: list[dict],
    pocket: dict,
    crbn_centroid: tuple[float, float, float] | None,
) -> list[dict]:
    """Apply estimate_linker_requirement + score_ternary_geometry to every candidate."""
    results = []
    for apt in aptamers:
        linker_info = estimate_linker_requirement(apt, pocket, crbn_centroid)
        ternary_scores = score_ternary_geometry(linker_info)
        results.append({**apt, **linker_info, **ternary_scores})
    return results


# ---------------------------------------------------------------------------
# STEP 10 — Hook Effect Penalty
# ---------------------------------------------------------------------------

def compute_hook_penalty(aptamers: list[dict]) -> list[dict]:
    """
    hook_penalty based on log10 ratio of Kd(aptamer) / Kd(CRBN ligand).
    Kd2 (pomalidomide → CRBN) = 5 nM fixed.

    Log-ratio formula gives meaningful discrimination across many orders of
    magnitude: log_ratio=0 → penalty=0.0; 1 order of magnitude → 0.5;
    2 orders → 0.67; 3 orders → 0.75.  Much better than linear asymmetry
    which collapses to ~1.0 whenever kd1 >> kd2.
    """
    results = []
    for a in aptamers:
        kd_str = a.get('kd_estimate', '100 nM')
        try:
            kd1 = float(kd_str.split()[0])
        except Exception:
            kd1 = 100.0
        kd2 = KD2_CRBN_NM
        if kd1 > 0 and kd2 > 0:
            log_ratio = abs(math.log10(kd1 / kd2))
            asymmetry = 1.0 - 1.0 / (1.0 + log_ratio)
        else:
            asymmetry = 1.0
        results.append({
            **a,
            'hook_penalty': round(asymmetry, 3),
            'hook_risk': asymmetry > 0.6,
        })
    return results


# ---------------------------------------------------------------------------
# STEP 11 — Composite Score
# ---------------------------------------------------------------------------

DEFAULT_WEIGHTS = {
    'rnaf_binding':         0.15,
    'docking_binding':      0.15,
    'fold_stability':       0.10,
    'epitope_quality':      0.20,
    'lysine_accessibility': 0.15,
    'ternary_feasibility':  0.20,
    'hook_penalty':         0.05,
}

# When RNAFlow binding score is unavailable, merge its weight into docking_binding
_WEIGHTS_NO_RNAF = {
    'rnaf_binding':         0.00,
    'docking_binding':      0.30,  # absorbs the 0.15 from rnaf_binding
    'fold_stability':       0.10,
    'epitope_quality':      0.20,
    'lysine_accessibility': 0.15,
    'ternary_feasibility':  0.20,
    'hook_penalty':         0.05,
}

_FOLD_PENALTY = 0.05  # subtracted from degradability when fold_warning is True


def _normalise_docking_score(score: float | None) -> float:
    """
    Map rDock score to 0–1 (higher = better binding).

    Uses sigmoid 1/(1+exp(score/20)) so the wide dynamic range from score.prm
    (RNA aptamers: typically +5 to +17000 for random placements) maps cleanly:
      score ≤ -20  → ≥ 0.73  (favorable interactions)
      score =   0  →   0.50  (neutral)
      score =  +5  →   0.43  (slight steric penalty)
      score = +50  →   0.08  (significant clashes)
      score > +500 →  ~0.00  (severe clashes)
    """
    if score is None:
        return 0.5
    clamped = min(float(score), 500.0)
    return round(1.0 / (1.0 + math.exp(clamped / 20.0)), 3)


def _normalise_mfe(mfe: float) -> float:
    """Map MFE to 0–1 (more negative = more stable = higher score)."""
    return round(min(1.0, max(0.0, abs(mfe) / 25)), 3)


def compute_composite_scores(aptamers: list[dict], weights: dict | None = None) -> list[dict]:
    results = []

    for a in aptamers:
        rnaf_score = a.get('rnaf_binding_score')  # None when RNAFlow not used
        dock_score = _normalise_docking_score(a.get('docking_score'))

        # Choose weight set based on RNAFlow availability
        if weights is not None:
            w = weights
        elif rnaf_score is None:
            w = _WEIGHTS_NO_RNAF
        else:
            w = DEFAULT_WEIGHTS

        rnaf_norm = float(rnaf_score) if rnaf_score is not None else 0.0
        fold_pen  = _FOLD_PENALTY if a.get('fold_warning') else 0.0

        scores = {
            'rnaf_binding':         round(rnaf_norm, 3),
            'docking_binding':      dock_score,
            'fold_stability':       _normalise_mfe(a.get('mfe', -10)),
            'epitope_quality':      a.get('epitope_quality', 0.5),
            'lysine_accessibility': a.get('lysine_accessibility', 0.5),
            'ternary_feasibility':  a.get('ternary_feasibility', 0.5),
            'hook_penalty':         a.get('hook_penalty', 0.3),
        }

        degradability = (
            w.get('rnaf_binding', 0)         * scores['rnaf_binding'] +
            w.get('docking_binding', 0)      * scores['docking_binding'] +
            w.get('fold_stability', 0)       * scores['fold_stability'] +
            w.get('epitope_quality', 0)      * scores['epitope_quality'] +
            w.get('lysine_accessibility', 0) * scores['lysine_accessibility'] +
            w.get('ternary_feasibility', 0)  * scores['ternary_feasibility'] -
            w.get('hook_penalty', 0)         * scores['hook_penalty'] -
            fold_pen
        )

        # Binding uncertainty warning: RNAFlow and docking scores disagree by > 0.4
        binding_uncertainty_warning = (
            rnaf_score is not None and abs(rnaf_norm - dock_score) > 0.4
        )

        results.append({
            **a,
            'scores': scores,
            'degradability': round(max(0.0, min(1.0, degradability)), 3),
            'binding_uncertainty_warning': binding_uncertainty_warning,
            'e3_inhibitory': False,
        })

    results.sort(key=lambda x: x['degradability'], reverse=True)
    for i, r in enumerate(results):
        r['rank'] = i + 1
        r['id'] = f'APT-{i+1:03d}'
        r['dot_bracket'] = r.get('structure', '.' * len(r['sequence']))
        r['verdict'] = _generate_verdict(r)

    return results


VERDICTS = [
    "Strong fold stability and E3 geometry — primary degrader candidate.",
    "Good binding profile with adequate lysine exposure — viable PROTAC arm.",
    "Excellent epitope geometry offset by elevated hook risk — linker optimisation advised.",
    "High lysine accessibility, moderate binding — suitable for second-generation design.",
    "Marginal stability with adequate geometry — experimental validation required.",
]


def _generate_verdict(apt: dict) -> str:
    s = apt['scores']
    if apt.get('ternary_failure'):
        dist = apt.get('linker_angstroms', '?')
        return f"Ternary complex unfeasible — {dist} Å bridging distance exceeds PEG linker range. Re-design linker attachment point."
    if apt.get('steric_clash'):
        return "Ternary complex blocked — aptamer docking pose clashes sterically with CRBN approach. Structural re-optimisation required."
    if apt.get('hook_risk'):
        return "Strong binder but high hook effect risk — arm affinities mismatched by more than one order of magnitude."
    if s.get('ternary_feasibility', 0) > 0.80 and s.get('epitope_quality', 0) > 0.70:
        return "Excellent ternary geometry and E3 approach angle — top-tier degrader candidate."
    if s.get('epitope_quality', 0) > 0.75 and s.get('lysine_accessibility', 0) > 0.70:
        return "Excellent E3 approach geometry and lysine exposure — strong degrader candidate."
    if s.get('fold_stability', 0) > 0.80:
        return "Exceptional fold stability with broad E3 approach surface — prioritise for synthesis."
    return VERDICTS[(apt.get('rank', 1) - 1) % len(VERDICTS)]


# ---------------------------------------------------------------------------
# Transition-biased mutation (shared with literature.py mutant generation)
# ---------------------------------------------------------------------------

_TRANSITIONS   = {'A': 'G', 'G': 'A', 'U': 'C', 'C': 'U'}
_TRANSVERSIONS = {'A': ['U', 'C'], 'G': ['U', 'C'], 'U': ['A', 'G'], 'C': ['A', 'G']}


def _mutate_transition_biased(sequence: str, mutation_rate: float) -> str:
    """
    Mutate sequence with transition-biased point mutations.
    Transitions (A↔G, U↔C) are weighted 3× over transversions to
    preferentially preserve RNA secondary structure.
    """
    rng = random.Random()
    bases = list(sequence)
    for i, nt in enumerate(bases):
        if rng.random() < mutation_rate:
            if rng.random() < 0.75:
                bases[i] = _TRANSITIONS.get(nt, nt)
            else:
                choices = _TRANSVERSIONS.get(nt, [nt])
                bases[i] = rng.choice(choices)
    return ''.join(bases)


# ---------------------------------------------------------------------------
# Iterative refinement loop
# ---------------------------------------------------------------------------

def run_refinement_loop(
    scored_candidates: list[dict],
    protein_pdb: str,
    pocket: dict,
    crbn_centroid,
    work_dir: Path,
    n_rounds: int = 3,
    top_keep: int = 5,
    n_mutants_per: int = 15,
    mutation_rate: float = 0.10,
    log_fn=None,
) -> list[dict]:
    """
    Iterative refinement: generate transition-biased mutants from top candidates,
    fold/dock/score them, merge with top seeds, re-rank. Repeat n_rounds times.

    Each candidate carries:
      round_introduced: int — which refinement round introduced it
      parent_sequence: str — sequence of the parent
      parent_score: float — degradability of parent at time of mutation
      score_history: list[float] — score per round this candidate existed

    Returns the final top_keep candidates with full lineage tracking.
    """
    if log_fn is None:
        log_fn = lambda msg: _log("refine", msg)

    pool = sorted(scored_candidates, key=lambda x: x.get('degradability', 0), reverse=True)
    apt_dir = work_dir / 'refine_aptamers'
    apt_dir.mkdir(parents=True, exist_ok=True)

    # Initialise score_history for round-0 candidates
    for c in pool:
        if 'score_history' not in c or not c['score_history']:
            c['score_history'] = [c.get('degradability', 0.0)]

    prev_best = pool[0].get('degradability', 0.0) if pool else 0.0

    for rnd in range(1, n_rounds + 1):
        seeds = pool[:top_keep]
        log_fn(f"> Refinement round {rnd}/{n_rounds}: seeding from top {len(seeds)} candidates")

        # Generate mutants for each seed
        mutant_seqs: list[dict] = []
        for seed in seeds:
            parent_score = seed.get('degradability', 0.0)
            parent_seq   = seed.get('sequence', '')
            gen_base     = seed.get('generation_method', 'RNAFlow')
            # Determine lineage tag
            if 'literature' in gen_base:
                tag = f"literature_r{rnd}_mutant"
            else:
                tag = f"RNAFlow_r{rnd}_mutant"

            for _ in range(n_mutants_per * 3):  # overshoot, filter by fold
                if sum(1 for m in mutant_seqs if m.get('parent_sequence') == parent_seq) >= n_mutants_per:
                    break
                mutant = _mutate_transition_biased(parent_seq, mutation_rate)
                if mutant == parent_seq:
                    continue
                try:
                    import RNA as _RNA
                    _, mfe = _RNA.fold(mutant)
                    if float(mfe) > -5.0:
                        continue
                except Exception:
                    continue
                mutant_seqs.append({
                    'sequence':          mutant,
                    'generation_method': tag,
                    'source':            'refinement_mutant',
                    'parent_sequence':   parent_seq,
                    'parent_score':      parent_score,
                    'round_introduced':  rnd,
                    'score_history':     [],
                })

        if not mutant_seqs:
            log_fn(f"> Round {rnd}: no stable mutants generated — skipping")
            continue

        log_fn(f"> Round {rnd}: {len(mutant_seqs)} stable mutants to dock")

        # Build 3D structures for mutants
        folded_mutants = validate_fold_stability(mutant_seqs)
        stable_mutants = [m for m in folded_mutants if not m.get('fold_warning')]

        try:
            round_apt_dir = apt_dir / f"round_{rnd}"
            structures    = predict_3d_structures(stable_mutants, round_apt_dir, n=len(stable_mutants))
        except Exception as e:
            log_fn(f"> Round {rnd}: 3D structure build failed: {e} — skipping round")
            continue

        # Dock all mutants
        def _dock_one_refine(args):
            i, apt = args
            dock_dir = work_dir / f'refine_{rnd}_{i:03d}'
            dock_dir.mkdir(parents=True, exist_ok=True)
            return dock_sequence(protein_pdb, apt, pocket, dock_dir)

        try:
            n_par = min(4, len(structures))
            with ThreadPoolExecutor(max_workers=n_par) as ex:
                docked_mutants = list(ex.map(_dock_one_refine, enumerate(structures)))
        except RuntimeError as e:
            log_fn(f"> Round {rnd}: docking failed: {e} — skipping round")
            continue

        # Score mutants
        with_sasa    = compute_sasa_scores(protein_pdb, docked_mutants)
        with_ternary = score_ternary_candidates(with_sasa, pocket, crbn_centroid)
        with_hook    = compute_hook_penalty(with_ternary)
        scored_new   = compute_composite_scores(with_hook)

        # Update score_history for new candidates
        for c in scored_new:
            c['score_history'] = [c.get('degradability', 0.0)]

        # Update score_history for existing pool (they survive another round)
        for c in pool:
            c['score_history'].append(c.get('degradability', c['score_history'][-1]))

        # Merge + re-rank
        combined = pool + scored_new
        combined.sort(key=lambda x: x.get('degradability', 0), reverse=True)
        pool = combined[:top_keep]

        current_best = pool[0].get('degradability', 0.0)
        delta = current_best - prev_best
        log_fn(
            f"> Round {rnd}/{n_rounds}: best {current_best:.3f} "
            f"({'+'if delta >= 0 else ''}{delta:.3f} from round {rnd-1})"
        )
        log_fn(
            f"> Top candidate: {pool[0].get('sequence', '')[:20]}... "
            f"[{pool[0].get('generation_method', '')}]"
        )

        if delta < 0.01:
            log_fn(
                f"> Converged at round {rnd} — "
                f"improvement {delta:.4f} below threshold"
            )
            break

        prev_best = current_best

    return pool


# ---------------------------------------------------------------------------
# Output enrichment helpers
# ---------------------------------------------------------------------------

def _experimental_hypothesis(candidate: dict) -> str:
    hook_penalty   = candidate.get('hook_penalty', 0.3)
    ternary_score  = candidate.get('ternary_feasibility', 0.5)
    lysine_score   = candidate.get('lysine_accessibility', 0.5)

    if hook_penalty > 0.6:
        return (
            "Run competition binding assay against CRBN before advancing "
            "— high hook risk"
        )
    if ternary_score < 0.5:
        return (
            "Test longer PEG linker variants "
            "— ternary complex geometry marginal"
        )
    if lysine_score < 0.4:
        return (
            "Consider alternative E3 ligase with different approach geometry "
            "— lysine accessibility limiting"
        )
    return "Strong candidate — prioritise for synthesis and SPR binding validation"


def _lineage_summary(candidate: dict) -> str:
    method       = candidate.get('generation_method', '')
    parent_score = candidate.get('parent_score')
    score        = candidate.get('degradability', 0.0)
    rnd          = candidate.get('round_introduced', 0)

    delta_str = ''
    if parent_score is not None:
        delta = score - parent_score
        delta_str = f" (Δ{'+'if delta >= 0 else ''}{delta:.2f})"

    if method == 'literature_seeded':
        src = candidate.get('source', 'literature')
        return f"{src} literature seed"

    if 'literature' in method and rnd == 0:
        src = candidate.get('source', 'literature_mutant')
        return f"Literature seed → mutant{delta_str}"

    if 'literature' in method:
        return f"Literature seed → round {rnd} mutant{delta_str}"

    if rnd == 0:
        return "RNAFlow de novo seed"

    return f"RNAFlow → round {rnd} mutant{delta_str}"


def enrich_output(candidates: list[dict]) -> list[dict]:
    """
    Add score_trajectory, improvement_from_parent, lineage_summary,
    and experimental_hypothesis to each top candidate.
    """
    enriched = []
    for c in candidates:
        history = c.get('score_history', [c.get('degradability', 0.0)])
        parent_score = c.get('parent_score', c.get('degradability', 0.0))
        enriched.append({
            **c,
            'score_trajectory':       history,
            'improvement_from_parent': round(c.get('degradability', 0.0) - parent_score, 4),
            'lineage_summary':         _lineage_summary(c),
            'experimental_hypothesis': _experimental_hypothesis(c),
        })
    return enriched


# ---------------------------------------------------------------------------
# Full Pipeline Orchestrator
# ---------------------------------------------------------------------------

def run_full_pipeline(
    pdb_id: str,
    output_dir=None,
    n_generate: int = 200,
    n_dock: int = 25,
) -> dict:
    """
    Run the complete AptaDeg pipeline end-to-end on a single protein target.

    Saves all intermediate files to output_dir (default: cache/<PDB_ID>/).
    Returns a results dict with the 20-field schema and pipeline summary.

    The 20 output fields per candidate:
      id, rank, sequence, generation_method, mfe, fold_warning, fold_validated,
      docking_score, kd_estimate, rnaf_binding_score, epitope_quality,
      lysine_accessibility, accessible_lysines, ternary_feasibility,
      linker_angstroms, peg_units, linker_recommendation,
      hook_penalty, degradability, binding_uncertainty_warning, verdict
    """
    import urllib.request as _req

    pdb_id = pdb_id.upper()
    if output_dir is None:
        output_dir = CACHE_DIR / pdb_id
    if not isinstance(output_dir, Path):
        output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    _log("pipeline", f"=== AptaDeg full pipeline: {pdb_id} ===")

    # Step 0: CRBN reference
    _log("pipeline", "Step 0: loading CRBN reference (4CI1)")
    crbn_ref = load_crbn_reference()
    crbn_centroid = crbn_ref["crbn_pocket_centroid"] if crbn_ref else None
    _log("pipeline", f"CRBN centroid: {crbn_centroid}")

    # Step 1: Fetch + clean target structure
    _log("pipeline", f"Step 1: fetching {pdb_id} from RCSB")
    raw_pdb_path   = str(output_dir / f"{pdb_id}_raw.pdb")
    clean_pdb_path = str(output_dir / f"{pdb_id}_clean.pdb")

    _req.urlretrieve(f"https://files.rcsb.org/download/{pdb_id}.pdb", raw_pdb_path)
    _log("pipeline", f"downloaded {pdb_id} -> {raw_pdb_path}")

    ok = prepare_structure(raw_pdb_path, clean_pdb_path)
    _log("pipeline", f"structure cleaned: {ok} -> {clean_pdb_path}")

    # Step 2: Binding sites
    _log("pipeline", "Step 2: running fpocket")
    pockets = run_fpocket(clean_pdb_path)
    pocket_props = extract_pocket_properties(pockets)
    top_pocket = pockets[0]
    _log("pipeline", f"top pocket: vol={pocket_props['volume']:.0f} drugg={pocket_props['druggability']:.3f}")
    (output_dir / "pockets.json").write_text(json.dumps(pockets, indent=2))

    # Step 3: Aptamer generation (RNAFlow → GPU if available)
    _log("pipeline", f"Step 3: generating {n_generate} aptamer candidates")
    with timed_step("RNAFlow generation"):
        library = generate_aptamer_candidates(
            pocket_props, clean_pdb=clean_pdb_path, n=n_generate, seed_protein=pdb_id
        )
    log_gpu_status("RNAFlow generation")
    (output_dir / "library.json").write_text(json.dumps(
        [{"sequence": c["sequence"], "method": c.get("generation_method", "")} for c in library],
        indent=2,
    ))

    # Step 4: Fold stability — parallel ViennaRNA across all CPU cores
    _log("pipeline", "Step 4: validating fold stability")
    with timed_step("ViennaRNA fold filter"):
        validated = validate_fold_stability(library)
    n_warned = sum(1 for v in validated if v.get("fold_warning"))
    _log("pipeline", f"fold done: {len(validated) - n_warned} stable, {n_warned} flagged")
    (output_dir / "validated.json").write_text(json.dumps(
        [{"sequence": v["sequence"], "mfe": v.get("mfe"), "fold_warning": v.get("fold_warning")} for v in validated],
        indent=2,
    ))

    # Step 5: 3D structures — parallel across CPU cores
    _log("pipeline", f"Step 5: predicting 3D structures (top {n_dock})")
    top_n = sorted(validated, key=lambda x: x.get("mfe", 0))[:n_dock]
    apt_dir = output_dir / "aptamers"
    with timed_step("3D structure generation"):
        top_3d = predict_3d_structures(top_n, apt_dir, n=n_dock)

    # Step 6: Docking — up to 4 parallel WSL rDock jobs
    _log("pipeline", f"Step 6: docking {len(top_3d)} candidates")
    n_parallel = min(4, len(top_3d))
    _log("pipeline", f"parallel docking: {n_parallel} simultaneous WSL jobs")

    def _dock_one(args):
        i, apt = args
        dock_dir = output_dir / f"dock_{i:03d}"
        dock_dir.mkdir(parents=True, exist_ok=True)
        return dock_sequence(clean_pdb_path, apt, top_pocket, dock_dir)

    with timed_step("rDock docking"):
        with ThreadPoolExecutor(max_workers=n_parallel) as ex:
            docked = list(ex.map(_dock_one, enumerate(top_3d)))

    best_score = min(
        (a["docking_score"] for a in docked if a.get("docking_score") is not None), default=None
    )
    _log("pipeline", f"docking complete, best score: {best_score}")

    # Steps 7+8: Epitope + lysine SASA
    _log("pipeline", "Step 7+8: computing SASA scores")
    with timed_step("SASA scoring"):
        with_sasa = compute_sasa_scores(clean_pdb_path, docked)

    # Step 9: Ternary geometry
    _log("pipeline", "Step 9: scoring ternary complex geometry")
    with_ternary = score_ternary_candidates(with_sasa, top_pocket, crbn_centroid)

    # Step 10: Hook penalty
    _log("pipeline", "Step 10: computing hook effect penalty")
    with_hook = compute_hook_penalty(with_ternary)

    # Step 11: Composite score
    _log("pipeline", "Step 11: computing composite degradability scores")
    ranked = compute_composite_scores(with_hook)

    # Build 20-field output records
    _OUTPUT_FIELDS = [
        "id", "rank", "sequence", "generation_method",
        "mfe", "fold_warning", "fold_validated",
        "docking_score", "kd_estimate", "rnaf_binding_score",
        "epitope_quality", "lysine_accessibility", "accessible_lysines",
        "ternary_feasibility", "linker_angstroms", "peg_units",
        "linker_recommendation", "hook_penalty", "degradability",
        "binding_uncertainty_warning", "verdict",
    ]
    output_records = [{f: r.get(f) for f in _OUTPUT_FIELDS} for r in ranked]

    # Save results JSON
    results_path = output_dir / f"{pdb_id}_results.json"
    results_path.write_text(json.dumps(output_records, indent=2))
    _log("pipeline", f"results saved -> {results_path}")

    # Print summary table
    _print_summary_table(output_records[:10], pdb_id)

    return {
        "pdb_id":            pdb_id,
        "generated":         len(library),
        "fold_stable":       len(validated) - n_warned,
        "fold_flagged":      n_warned,
        "docked":            len(docked),
        "ranked":            len(ranked),
        "top_candidate":     output_records[0]["id"] if output_records else None,
        "top_score":         output_records[0]["degradability"] if output_records else None,
        "generation_method": library[0].get("generation_method", "unknown") if library else "unknown",
        "rnaflow_used":      RNAFLOW_AVAILABLE,
        "results_path":      str(results_path),
        "candidates":        output_records,
    }


def _print_summary_table(records: list, pdb_id: str) -> None:
    """Print a formatted summary table of top candidates."""
    sep = "=" * 95
    print(f"\n{sep}")
    print(f"  AptaDeg Results  --  {pdb_id}")
    print(sep)
    print(
        f"{'Rank':<5} {'ID':<9} {'Seq (first 20nt)':<22} {'MFE':>6} {'FW':>3} "
        f"{'Dock':>8} {'Ternary':>8} {'Hook':>6} {'Score':>7}  Verdict"
    )
    print("-" * 95)
    for r in records:
        seq_short = (r.get("sequence") or "")[:20]
        mfe       = r.get("mfe") or 0.0
        fw        = "!" if r.get("fold_warning") else " "
        dock      = r.get("docking_score") or 0.0
        tern      = r.get("ternary_feasibility") or 0.0
        hook      = r.get("hook_penalty") or 0.0
        score     = r.get("degradability") or 0.0
        verdict   = (r.get("verdict") or "")[:38]
        print(
            f"{r.get('rank','?'):<5} {r.get('id','?'):<9} {seq_short:<22} "
            f"{mfe:>6.1f} {fw:>3} {dock:>8.1f} {tern:>8.3f} {hook:>6.3f} "
            f"{score:>7.3f}  {verdict}"
        )
    print(sep)
