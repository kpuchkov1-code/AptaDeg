"""
Standalone RNAFlow inference script that runs inside WSL2.

Called by pipeline.py via:
    wsl -d Ubuntu -- bash -c "source /opt/rnaflow_env/bin/activate && \
        python /mnt/c/.../run_rnaflow_wsl.py --protein ... --output ..."

Outputs a JSON array of candidate dicts to --output (must be a /mnt/c/... path).
"""
import argparse
import json
import os
import random
import sys
import warnings

warnings.filterwarnings("ignore")

RNAFLOW_ROOT = "/mnt/c/Users/Kirill/rnaflow"
for _p in [
    RNAFLOW_ROOT,
    os.path.join(RNAFLOW_ROOT, "rnaflow", "utils"),
    os.path.join(RNAFLOW_ROOT, "geometric_rna_design", "src"),
    os.path.join(RNAFLOW_ROOT, "RoseTTAFold2NA", "network"),
]:
    if os.path.isdir(_p) and _p not in sys.path:
        sys.path.insert(0, _p)

import numpy as np
import torch
from Bio.PDB import PDBParser


def _is_compositionally_valid(seq):
    if not seq:
        return False
    for nt in "ACGU":
        if seq.count(nt) / len(seq) > 0.60:
            return False
    return True


def _extract_prot_backbone(pdb_path):
    AA3 = {
        "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
        "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
        "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
        "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    }
    try:
        parser = PDBParser(QUIET=True)
        structure = parser.get_structure("prot", pdb_path)
        seq_chars, coords_list = [], []
        for residue in structure.get_residues():
            if residue.get_resname() not in AA3:
                continue
            try:
                n_arr  = residue["N"].get_vector().get_array()
                ca_arr = residue["CA"].get_vector().get_array()
                c_arr  = residue["C"].get_vector().get_array()
            except KeyError:
                continue
            seq_chars.append(AA3[residue.get_resname()])
            coords_list.append([n_arr, ca_arr, c_arr])
        if not coords_list:
            return None, None
        coords = torch.tensor(np.array(coords_list), dtype=torch.float32)
        return "".join(seq_chars), coords
    except Exception as exc:
        print(f"[rnaflow_wsl] backbone extraction failed: {exc}", file=sys.stderr)
        return None, None


def _build_rna_backbone(rna_seq, device):
    """Minimal straight-ladder RNA backbone (~3.4 Å rise/residue)."""
    n = len(rna_seq)
    rows = []
    for i in range(n):
        z = float(i) * 3.4
        rows.append([[0.0, 0.0, z], [1.5, 0.0, z], [3.0, 0.0, z]])
    return torch.tensor(rows, dtype=torch.float32, device=device)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--protein",     required=True)
    ap.add_argument("--output",      required=True)
    ap.add_argument("--n_samples",   type=int,   default=200)
    ap.add_argument("--temperature", type=float, default=0.9)
    ap.add_argument("--rna_len",     type=int,   default=26)
    ap.add_argument("--device",      default="cuda")
    ap.add_argument("--seed",        type=int,   default=42)
    args = ap.parse_args()

    device = args.device if torch.cuda.is_available() else "cpu"
    print(f"[rnaflow_wsl] device: {device}", file=sys.stderr)
    if device == "cuda":
        print(f"[rnaflow_wsl] GPU: {torch.cuda.get_device_name(0)}", file=sys.stderr)

    ckpt = os.path.join(RNAFLOW_ROOT, "checkpoints", "seq-sim-rnaflow-epoch32.ckpt")
    from rnaflow.models.inverse_folding import InverseFoldingModel
    model = InverseFoldingModel.load_from_checkpoint(ckpt, map_location=device, strict=False)
    model.eval()
    model.to(device)
    model.data_featurizer.device = device
    print("[rnaflow_wsl] model loaded on GPU", file=sys.stderr)

    prot_seq, prot_coords = _extract_prot_backbone(args.protein)
    if prot_seq is None:
        print("[rnaflow_wsl] ERROR: backbone extraction failed", file=sys.stderr)
        sys.exit(1)

    prot_coords = prot_coords.to(device)
    rng = random.Random(args.seed)
    candidates = []

    # Featurize the protein backbone ONCE — it is the same for all samples.
    # This is the expensive step (~1-2 min for a 300-residue protein on CPU).
    # Reusing prot_g / pc across samples gives ~200x speedup.
    print("[rnaflow_wsl] featurizing protein backbone (once)...", file=sys.stderr)
    with torch.no_grad():
        prot_g_cached, pc_cached = model.data_featurizer._featurize(
            prot_seq, prot_coords.unsqueeze(0), rna=False
        )
    print("[rnaflow_wsl] protein featurized — starting sequence sampling", file=sys.stderr)

    is_rna_base = torch.cat((
        torch.zeros((len(prot_seq),)),
        torch.ones((args.rna_len,)),
    ), dim=0).bool().to(device)

    with torch.no_grad():
        attempts = 0
        max_attempts = args.n_samples * 4
        while len(candidates) < args.n_samples and attempts < max_attempts:
            attempts += 1
            if attempts % 20 == 0:
                print(f"[rnaflow_wsl] {len(candidates)}/{args.n_samples} done "
                      f"({attempts} attempts)", file=sys.stderr)
            init_rna = "".join(rng.choice("ACGU") for _ in range(args.rna_len))
            try:
                rna_coords = _build_rna_backbone(init_rna, device)
                rna_g, rc  = model.data_featurizer._featurize(
                    init_rna, rna_coords.unsqueeze(0))
                cg = model.data_featurizer._connect_graphs(
                    prot_g_cached, rna_g, pc_cached, rc)
                samples, _ = model.model.sample(
                    cg, 1, None,
                    temperature=args.temperature,
                    is_rna_mask=is_rna_base,
                )
                pred = samples[0, is_rna_base]
                seq = "".join(
                    model.data_featurizer.rna_num_to_letter.get(x, "X")
                    for x in pred.tolist()
                )
            except Exception as exc:
                print(f"[rnaflow_wsl] attempt {attempts} failed: {exc}", file=sys.stderr)
                continue

            if not _is_compositionally_valid(seq):
                continue

            candidates.append({
                "sequence": seq,
                "generation_method": "RNAFlow InverseFolding (WSL GPU)",
                "generation_basis": (
                    f"RNAFlow inverse folding // GPU:{device} // "
                    f"temperature={args.temperature} // len {len(seq)}nt"
                ),
                "rnaf_binding_score": None,
            })

    print(f"[rnaflow_wsl] generated {len(candidates)} / {args.n_samples} candidates "
          f"({attempts} attempts)", file=sys.stderr)
    with open(args.output, "w") as fh:
        json.dump(candidates, fh)


if __name__ == "__main__":
    main()
