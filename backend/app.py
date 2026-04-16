"""AptaDeg Flask backend — WebSocket + REST API.

Pipeline flow:
  0. crbn_load   — Load CRBN pomalidomide reference (4CI1)
  1. fetch       — Fetch target structure from RCSB/ESMFold
  2. clean       — Strip waters/heteroatoms (BioPython)
  3. fpocket     — Binding site detection (fpocket WSL) [CRITICAL]
  4. literature  — Scrape literature aptamers (parallel with generate)
  5. generate    — RNAFlow GPU + biased SELEX (parallel with literature)
  6. fold        — ViennaRNA MFE filter (parallel, all CPU cores) [CRITICAL]
  7. structures  — 3D backbone generation (rna-tools templates) [CRITICAL]
  8. docking     — rDock → HADDOCK (4 parallel WSL jobs) [CRITICAL]
  9. scoring     — Epitope/lysine/ternary/hook/composite scores
  10. refine_1   — Refinement round 1 (mutate top-5, dock, re-rank)
  11. refine_2   — Refinement round 2
  12. refine_3   — Refinement round 3
"""

import re
import threading
import time
import traceback
import uuid
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_socketio import SocketIO

import pipeline as pl
import literature as lit

app = Flask(__name__)
CORS(app, resources={r'/api/*': {'origins': '*'}})
socketio = SocketIO(app, cors_allowed_origins='*', async_mode='threading')

CACHE_DIR = Path(__file__).parent / 'cache'
CACHE_DIR.mkdir(exist_ok=True)

N_GENERATE = 200   # RNAFlow candidates per run
N_DOCK     = 12    # top candidates taken to 3D + docking

active_runs: dict[str, dict] = {}
_sid_to_run: dict[str, str] = {}   # socket session id → run_id


@socketio.on('disconnect')
def _on_disconnect():
    run_id = _sid_to_run.pop(request.sid, None)
    if run_id and run_id in active_runs:
        run = active_runs[run_id]
        if run['status'] == 'running':
            run['cancel'].set()
            run['status'] = 'cancelled'
            print(f"[cancel] run {run_id} cancelled — client disconnected")
    # Kill any WSL subprocesses (rbdock/rbcavity) still running for this session.
    # Without this, rDock child processes inside WSL survive wsl.exe being killed
    # and run indefinitely, consuming CPU until the machine is rebooted.
    pl.kill_all_wsl_processes()


def _check_cancel(run_id: str) -> None:
    """Raise RuntimeError if the run has been cancelled."""
    run = active_runs.get(run_id)
    cancel_event = run and run.get('cancel')
    if cancel_event and cancel_event.is_set():
        raise RuntimeError("Pipeline cancelled — client disconnected")

# ---------------------------------------------------------------------------
# Protein fetching helpers
# ---------------------------------------------------------------------------

def _resolve_protein_names(pdb_id: str) -> list[str]:
    """
    Query RCSB REST API to get human-readable protein names for a PDB entry.
    Returns a list of names to try for literature search (gene names first,
    then molecule descriptions, then PDB ID as last resort).
    Falls back gracefully — never raises.
    """
    names: list[str] = []
    try:
        r = requests.get(
            f'https://data.rcsb.org/rest/v1/core/entry/{pdb_id.upper()}',
            timeout=10,
        )
        if r.status_code != 200:
            return [pdb_id]
        data = r.json()
        entity_ids = (
            data.get('rcsb_entry_container_identifiers', {})
                .get('polymer_entity_ids', ['1'])
        )
    except Exception:
        return [pdb_id]

    for eid in entity_ids[:3]:  # check first 3 entities
        try:
            er = requests.get(
                f'https://data.rcsb.org/rest/v1/core/polymer_entity/{pdb_id.upper()}/{eid}',
                timeout=10,
            )
            if er.status_code != 200:
                continue
            ed = er.json()
            desc = ed.get('rcsb_polymer_entity', {}).get('pdbx_description', '')
            if desc and desc not in names:
                names.append(desc)
            for g in ed.get('rcsb_polymer_entity', {}).get('rcsb_gene_name', []):
                val = g.get('value', '')
                if val and val not in names:
                    names.insert(0, val)  # gene names first
        except Exception:
            continue

    return names if names else [pdb_id]


def _fetch_pdb_rcsb(pdb_id: str):
    cache_path = CACHE_DIR / f'{pdb_id.upper()}.pdb'
    if cache_path.exists():
        return cache_path.read_text()
    r = requests.get(f'https://files.rcsb.org/download/{pdb_id.upper()}.pdb', timeout=15)
    if r.status_code == 200:
        cache_path.write_text(r.text)
        return r.text
    raise RuntimeError(f"RCSB returned HTTP {r.status_code} for {pdb_id}")


def _fetch_uniprot_sequence(uid: str) -> str | None:
    r = requests.get(f'https://rest.uniprot.org/uniprotkb/{uid}.fasta', timeout=10)
    if r.status_code == 200:
        lines = r.text.strip().split('\n')
        return ''.join(lines[1:])
    return None


def _fold_with_esmatlas(sequence: str) -> str | None:
    r = requests.post(
        'https://api.esmatlas.com/foldSequence/v1/pdb/',
        data=sequence, timeout=60,
    )
    if r.status_code == 200:
        return r.text
    return None


def _count_residues(pdb_text: str) -> int:
    seen = set()
    for line in pdb_text.splitlines():
        if line.startswith('ATOM'):
            seen.add((line[21], line[22:26].strip()))
    return len(seen)


def _count_lysines(pdb_text: str) -> int:
    seen = set()
    for line in pdb_text.splitlines():
        if line.startswith('ATOM') and line[17:20].strip() == 'LYS':
            seen.add((line[21], line[22:26].strip()))
    return len(seen)


def _resolve_protein(id_str: str):
    """
    Resolve a protein identifier to a PDB structure.
    Tries RCSB (4-char PDB ID) then UniProt → ESMFold.
    Raises RuntimeError if unavailable (critical step).
    """
    id_clean = id_str.strip().upper()
    if len(id_clean) == 4 and id_clean.isalnum():
        pdb = _fetch_pdb_rcsb(id_clean)
        if pdb:
            return pdb, _count_residues(pdb), _count_lysines(pdb), id_clean, 'RCSB'
    seq = _fetch_uniprot_sequence(id_clean)
    if seq:
        pdb = _fold_with_esmatlas(seq[:400])
        if pdb:
            return pdb, _count_residues(pdb), _count_lysines(pdb), id_clean, 'ESMFold'
    raise RuntimeError(
        f"Could not resolve structure for '{id_str}'. "
        "Provide a valid 4-character PDB ID (e.g. 1YCR) or UniProt accession."
    )


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def _serialize_candidate(c: dict) -> dict:
    scores = c.get('scores', {})
    seq    = c.get('sequence', '')
    scaffold = 'G-quadruplex' if seq and seq.count('G') / max(1, len(seq)) > 0.35 else 'stem-loop'
    ternary_warning = None
    if c.get('ternary_failure'):
        ternary_warning = (
            f"Ternary unfeasible — {c.get('linker_angstroms', '?')} Å exceeds PEG linker range"
        )
    elif c.get('steric_clash'):
        ternary_warning = 'Steric clash — CRBN approach blocked'

    return {
        'id':    c.get('id', ''),
        'rank':  c.get('rank', 1),
        'sequence':    seq,
        'dot_bracket': c.get('dot_bracket') or c.get('structure', ''),
        'generation_method':  c.get('generation_method', 'RNAFlow'),
        'generation_bias':    c.get('generation_basis', ''),
        'scaffold':    scaffold,
        'mfe':         c.get('mfe'),
        'docking_score':  c.get('docking_score'),
        'kd_estimate':    c.get('kd_estimate', ''),
        'degradability_score':        c.get('degradability', 0.0),
        'fold_stability_score':       scores.get('fold_stability', 0.5),
        'binding_score':              scores.get('docking_binding', 0.5),
        'epitope_quality_score':      scores.get('epitope_quality', 0.5),
        'lysine_accessibility_score': scores.get('lysine_accessibility', 0.5),
        'ternary_feasibility_score':  scores.get('ternary_feasibility', 0.5),
        'hook_penalty':               scores.get('hook_penalty', 0.3),
        'accessible_lysines': c.get('accessible_lysines'),
        'contact_residues':   c.get('contact_residues'),
        'linker_display':   (c.get('linker_recommendation') or '').replace('LINKER: ', ''),
        'linker_angstroms': c.get('linker_angstroms'),
        'peg_units':        c.get('peg_units'),
        'hook_result':      {'high_risk': bool(c.get('hook_risk', False))},
        'ternary_warning':  ternary_warning,
        'fold_warning':     c.get('fold_warning', False),
        'verdict':          c.get('verdict', ''),
        # Refinement enrichment fields
        'score_trajectory':        c.get('score_trajectory', [c.get('degradability', 0.0)]),
        'improvement_from_parent': c.get('improvement_from_parent', 0.0),
        'lineage_summary':         c.get('lineage_summary', ''),
        'experimental_hypothesis': c.get('experimental_hypothesis', ''),
        'round_introduced':        c.get('round_introduced', 0),
    }


# ---------------------------------------------------------------------------
# WebSocket emit
# ---------------------------------------------------------------------------

def _emit_step(run_id, step, status, message='', elapsed=None, progress=None):
    payload = {
        'run_id': run_id, 'step': step,
        'status': status, 'message': message,
        'elapsed': elapsed, 'progress': progress,
    }
    if run_id in active_runs:
        active_runs[run_id]['steps'][step] = {
            'status': status, 'message': message,
            'elapsed': elapsed, 'progress': progress,
        }
    socketio.emit('step_update', payload)


def _log_to_run(run_id: str, message: str):
    """Emit a log-only message without changing any step status."""
    socketio.emit('step_update', {
        'run_id': run_id, 'step': None,
        'status': None, 'message': message,
        'elapsed': None, 'progress': None,
    })


# ---------------------------------------------------------------------------
# Step progress weights (cumulative %)
# ---------------------------------------------------------------------------

_STEP_PROGRESS = {
    'crbn_load':  2,
    'fetch':      5,
    'clean':      8,
    'fpocket':    12,
    'literature': 22,   # parallel with generate
    'generate':   22,   # parallel with literature
    'fold':       28,
    'structures': 40,
    'docking':    60,
    'scoring':    65,
    'refine_1':   78,
    'refine_2':   89,
    'refine_3':   97,
}


# ---------------------------------------------------------------------------
# Background pipeline runner
# ---------------------------------------------------------------------------

def run_pipeline_async(run_id, protein_id, e3_ligase, cell_line):
    pipeline_start = time.time()
    try:
        run      = active_runs[run_id]
        work_dir = CACHE_DIR / protein_id.upper()
        work_dir.mkdir(parents=True, exist_ok=True)
        n_gen  = run.get('n_generate', N_GENERATE)
        n_dock = run.get('n_dock',     N_DOCK)

        def emit(step, status, msg='', t_start=None):
            elapsed = round(time.time() - t_start, 1) if t_start else None
            _emit_step(run_id, step, status, msg, elapsed, _STEP_PROGRESS.get(step))

        def log_msg(msg):
            _log_to_run(run_id, msg)

        # ── Step 0: CRBN reference ────────────────────────────────────────
        emit('crbn_load', 'running', 'Loading CRBN reference (4CI1)')
        t = time.time()
        crbn_ref      = pl.load_crbn_reference()
        crbn_centroid = crbn_ref['crbn_pocket_centroid'] if crbn_ref else None
        emit('crbn_load', 'complete',
             f'CRBN pomalidomide centroid: {crbn_centroid}', t)

        # ── Step 1: Fetch structure ───────────────────────────────────────
        emit('fetch', 'running', f'Fetching {protein_id} from RCSB / UniProt')
        t = time.time()
        pdb, residue_count, lysine_count, name, source = _resolve_protein(protein_id)
        raw_path   = str(work_dir / 'protein_raw.pdb')
        clean_path = str(work_dir / 'protein_clean.pdb')
        Path(raw_path).write_text(pdb)
        emit('fetch', 'complete',
             f'{residue_count} residues, {lysine_count} surface lysines ({source})', t)

        # ── Step 2: Clean structure ───────────────────────────────────────
        emit('clean', 'running', 'Stripping waters and HETATM records (BioPython)')
        t = time.time()
        pl.prepare_structure(raw_path, clean_path)
        emit('clean', 'complete', 'Structure cleaned', t)

        # ── Step 3: Binding sites (fpocket) ──────────────────────────────
        _check_cancel(run_id)
        emit('fpocket', 'running', 'Running fpocket binding site detection (WSL)')
        t = time.time()
        pockets      = pl.run_fpocket(clean_path)     # raises if fpocket missing
        top_pocket   = pockets[0]
        pocket_props = pl.extract_pocket_properties(pockets)
        emit('fpocket', 'complete',
             f'{len(pockets)} pockets found — top vol {top_pocket.get("volume", 0):.0f} Å³ '
             f'druggability {top_pocket.get("druggability", 0):.2f}', t)

        # ── Steps 4+5: Literature scraping + RNAFlow (parallel) ──────────
        _check_cancel(run_id)
        # Resolve human-readable protein names from PDB ID for literature search
        protein_names = _resolve_protein_names(protein_id)
        log_msg(f"> Resolved protein names: {', '.join(protein_names)}")
        emit('literature', 'running',
             f'Scraping literature for {", ".join(protein_names[:2])}')
        emit('generate',   'running', f'RNAFlow GPU generating {n_gen} candidates (WSL2)')

        lit_pool:  list[dict] = []
        gen_pool:  list[dict] = []
        lit_error: str | None = None

        def _run_literature():
            nonlocal lit_pool, lit_error
            try:
                # Try each resolved name; merge results
                all_lit: list[dict] = []
                seen_seqs: set[str] = set()
                for pname in protein_names:
                    found = lit.scrape_literature_aptamers(
                        pname, protein_id, log_fn=log_msg,
                    )
                    for apt in found:
                        if apt['sequence'] not in seen_seqs:
                            seen_seqs.add(apt['sequence'])
                            all_lit.append(apt)
                lit_pool[:] = all_lit
            except Exception as e:
                lit_error = str(e)

        def _run_generate():
            nonlocal gen_pool
            gen_pool = pl.generate_aptamer_candidates(
                pocket_props, clean_path, n=n_gen, seed_protein=protein_id,
            )

        t_par = time.time()
        with ThreadPoolExecutor(max_workers=2) as ex:
            fut_lit = ex.submit(_run_literature)
            fut_gen = ex.submit(_run_generate)
            fut_lit.result()
            fut_gen.result()

        if lit_error:
            emit('literature', 'failed',
                 f'Literature scraping failed (non-critical): {lit_error}',
                 t_par)
        else:
            emit('literature', 'complete',
                 f'{len(lit_pool)} sequences from literature + mutants',
                 t_par)

        gen_method = gen_pool[0].get('generation_method', 'biased SELEX') if gen_pool else 'none'
        emit('generate', 'complete',
             f'{len(gen_pool)} candidates ({gen_method[:45]})', t_par)

        # Merge pools, deduplicate by sequence
        all_seqs  = {c['sequence']: c for c in gen_pool}
        for c in lit_pool:
            all_seqs.setdefault(c['sequence'], c)
        combined_pool = list(all_seqs.values())

        # ── Step 6: Fold stability ────────────────────────────────────────
        _check_cancel(run_id)
        emit('fold', 'running',
             f'ViennaRNA MFE folding — {len(combined_pool)} sequences (parallel CPUs)')
        t = time.time()
        folded    = pl.validate_fold_stability(combined_pool)   # raises if ViennaRNA missing
        n_stable  = sum(1 for f in folded if not f.get('fold_warning'))
        n_flagged = len(folded) - n_stable
        emit('fold', 'complete',
             f'{n_stable} stable (MFE ≤ -5.0 kcal/mol), {n_flagged} flagged', t)

        # ── Step 7: 3D structures ─────────────────────────────────────────
        _check_cancel(run_id)
        top_n = sorted(folded, key=lambda x: x.get('mfe', 0))[:n_dock]
        emit('structures', 'running',
             f'Building 3D backbones for top {len(top_n)} candidates (rna-tools)')
        t = time.time()
        structures = pl.predict_3d_structures(top_n, work_dir / 'aptamers', n=n_dock)
        emit('structures', 'complete',
             f'{len(structures)} structures built (2AP6 / 2GKU / 3Q3Z templates)', t)

        # ── Step 8: Docking ───────────────────────────────────────────────
        _check_cancel(run_id)
        emit('docking', 'running',
             f'rDock protein-RNA docking — {len(structures)} candidates (4 parallel WSL jobs)')
        t = time.time()
        with ThreadPoolExecutor(max_workers=4) as ex:
            futures = []
            for i, apt in enumerate(structures):
                dock_dir = work_dir / f'dock_{i:03d}'
                dock_dir.mkdir(parents=True, exist_ok=True)
                futures.append(ex.submit(pl.dock_sequence, clean_path, apt, top_pocket, dock_dir))
            docked = [f.result() for f in futures]   # raises if no docking engine
        best = min((a.get('docking_score') or 0) for a in docked)
        emit('docking', 'complete',
             f'{len(docked)} docked — best rDock score {best:.1f}', t)

        # ── Step 9: Initial scoring ───────────────────────────────────────
        emit('scoring', 'running',
             'Computing epitope, lysine, ternary geometry, hook effect')
        t = time.time()
        scored = pl.compute_sasa_scores(clean_path, docked)
        scored = pl.score_ternary_candidates(scored, top_pocket, crbn_centroid)
        scored = pl.compute_hook_penalty(scored)
        ranked = pl.compute_composite_scores(scored)
        for c in ranked:
            c.setdefault('score_history', [c.get('degradability', 0.0)])
            c.setdefault('round_introduced', 0)
        top5 = ranked[:5]
        best_deg = top5[0]['degradability'] if top5 else 0.0
        emit('scoring', 'complete',
             f'Initial best degradability: {best_deg:.3f} — {len(top5)} candidates', t)

        # ── Steps 10-12: Refinement rounds ───────────────────────────────
        all_candidates = ranked

        for rnd in range(1, 4):
            _check_cancel(run_id)
            step_id = f'refine_{rnd}'
            emit(step_id, 'running',
                 f'Refinement round {rnd}/3 — mutating top-5, docking {5 * 15} mutants')
            t = time.time()
            try:
                all_candidates = pl.run_refinement_loop(
                    all_candidates,
                    protein_pdb=clean_path,
                    pocket=top_pocket,
                    crbn_centroid=crbn_centroid,
                    work_dir=work_dir,
                    n_rounds=1,
                    top_keep=5,
                    n_mutants_per=15,
                    mutation_rate=0.10,
                    log_fn=log_msg,
                )
                best_rnd = all_candidates[0]['degradability'] if all_candidates else 0.0
                emit(step_id, 'complete',
                     f'Round {rnd} best: {best_rnd:.3f}', t)
            except Exception as e:
                emit(step_id, 'failed',
                     f'Round {rnd} failed (non-critical): {e}', t)

        # ── Enrich top 5 and build results ────────────────────────────────
        top5_final = pl.enrich_output(all_candidates[:5])
        total_elapsed = round(time.time() - pipeline_start, 1)

        run['status']  = 'complete'
        run['results'] = {
            'protein_id':     protein_id.upper(),
            'n_pockets':      len(pockets),
            'n_generated':    len(gen_pool),
            'n_literature':   len(lit_pool),
            'n_stable':       n_stable,
            'n_docked':       len(docked),
            'candidates':     [_serialize_candidate(c) for c in top5_final],
            'pocket':         top_pocket,
            'total_elapsed':  total_elapsed,
        }
        socketio.emit('pipeline_complete', {
            'run_id': run_id, 'n_candidates': len(top5_final),
        })

    except Exception as exc:
        traceback.print_exc()
        if run_id in active_runs:
            active_runs[run_id]['status'] = 'failed'
            active_runs[run_id]['error']  = str(exc)
        socketio.emit('pipeline_failed', {'run_id': run_id, 'error': str(exc)})


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------

@app.get('/api/health')
def health():
    return jsonify({'status': 'ok', 'time': time.time()})


def _read_sequence_from_pdb(pdb_path: str) -> str:
    """Extract RNA sequence from PDB by reading residue names in order."""
    seen = {}  # resseq → resname (keep first occurrence)
    try:
        with open(pdb_path) as f:
            for line in f:
                if not line.startswith('ATOM'):
                    continue
                resname = line[17:20].strip()
                resseq  = int(line[22:26].strip())
                if resseq not in seen and resname in ('A', 'C', 'G', 'U'):
                    seen[resseq] = resname
    except Exception:
        return ''
    return ''.join(seen[k] for k in sorted(seen))


def _read_dock_score_from_sd(sd_path: str) -> float | None:
    """Parse the SCORE field from an rDock scored.sd file."""
    try:
        with open(sd_path) as f:
            lines = f.readlines()
        for i, line in enumerate(lines):
            if line.strip() == '>  <SCORE>':
                return float(lines[i + 1].strip())
    except Exception:
        pass
    return None


def _load_cached_candidates(protein_id: str) -> list[dict]:
    """
    Reconstruct docked candidate dicts from scored.sd + PDB files in the cache.
    Looks for dock_NNN/ dirs (initial) and refine_1_NNN/ dirs (round-1 refined).
    """
    work_dir = CACHE_DIR / protein_id.upper()
    candidates = []

    # Patterns: initial docking dirs and refine round-1 dirs
    patterns = [
        (work_dir.glob('dock_[0-9][0-9][0-9]'), 'initial', 0),
        (work_dir.glob('refine_1_[0-9][0-9][0-9]'), 'RNAFlow_r1_mutant', 1),
    ]
    for dirs, gen_method, rnd in patterns:
        for dock_dir in sorted(dirs):
            sd   = dock_dir / 'scored.sd'
            if not sd.exists():
                continue
            score = _read_dock_score_from_sd(str(sd))
            if score is None:
                continue
            # Find the aptamer PDB used for this dock (stored in first line of .sd)
            pdb_path = None
            try:
                first = open(sd).readline().strip()
                # Convert WSL path /mnt/c/... → Windows path
                if first.startswith('/mnt/'):
                    parts = first[5:].split('/', 1)
                    win = parts[0].upper() + ':/' + (parts[1] if len(parts) > 1 else '')
                    if Path(win).exists():
                        pdb_path = win
            except Exception:
                pass
            seq = _read_sequence_from_pdb(pdb_path) if pdb_path else ''
            candidates.append({
                'sequence':          seq or f'unknown_{dock_dir.name}',
                'docking_score':     score,
                'pdb_path':          pdb_path,
                'generation_method': gen_method,
                'round_introduced':  rnd,
                'source':            'cache',
            })
    return candidates


@app.post('/api/resume')
def resume_from_cache():
    """
    Load cached docking results for a protein, re-score them in memory (fast),
    and emit pipeline_complete so the frontend shows results immediately.
    """
    data       = request.get_json(silent=True) or {}
    protein_id = data.get('protein_id', '').strip().upper()
    socket_id  = data.get('socket_id', '')
    if not protein_id:
        return jsonify({'error': 'protein_id required'}), 400

    work_dir = CACHE_DIR / protein_id
    clean_path = str(work_dir / 'protein_clean.pdb')
    if not Path(clean_path).exists():
        return jsonify({'error': f'No cached results for {protein_id}'}), 404

    run_id = str(uuid.uuid4())
    active_runs[run_id] = {
        'status': 'running', 'protein_id': protein_id,
        'steps': {}, 'results': None, 'error': None,
        'cancel': threading.Event(),
    }
    if socket_id:
        _sid_to_run[socket_id] = run_id

    def _do_resume():
        try:
            candidates = _load_cached_candidates(protein_id)
            if not candidates:
                raise RuntimeError('No cached dock results found')

            # Re-score entirely in memory — no WSL needed
            crbn_ref      = pl.load_crbn_reference()
            crbn_centroid = crbn_ref['crbn_pocket_centroid'] if crbn_ref else None
            pocket_path   = work_dir / 'protein_clean_out'
            pockets       = pl._parse_fpocket_output(str(pocket_path)) if pocket_path.exists() else []
            top_pocket    = pockets[0] if pockets else {'centroid_x': 0, 'centroid_y': 0, 'centroid_z': 0, 'volume': 0, 'druggability': 0}

            scored = pl.compute_sasa_scores(clean_path, candidates)
            scored = pl.score_ternary_candidates(scored, top_pocket, crbn_centroid)
            scored = pl.compute_hook_penalty(scored)
            ranked = pl.compute_composite_scores(scored)
            for i, c in enumerate(ranked):
                c.setdefault('score_history', [c.get('degradability', 0.0)])
                c['rank'] = i + 1

            top5 = pl.enrich_output(ranked[:5])
            active_runs[run_id]['status']  = 'complete'
            active_runs[run_id]['results'] = {
                'protein_id':    protein_id,
                'n_pockets':     len(pockets),
                'n_generated':   len([c for c in candidates if c.get('round_introduced', 0) == 0]),
                'n_literature':  0,
                'n_stable':      len(candidates),
                'n_docked':      len(candidates),
                'candidates':    [_serialize_candidate(c) for c in top5],
                'pocket':        top_pocket,
                'total_elapsed': 0,
            }
            socketio.emit('pipeline_complete', {'run_id': run_id, 'n_candidates': len(top5)})
        except Exception as exc:
            traceback.print_exc()
            active_runs[run_id]['status'] = 'failed'
            active_runs[run_id]['error']  = str(exc)
            socketio.emit('pipeline_failed', {'run_id': run_id, 'error': str(exc)})

    threading.Thread(target=_do_resume, daemon=True).start()
    return jsonify({'run_id': run_id})


@app.post('/api/run')
def start_pipeline():
    data       = request.get_json(silent=True) or {}
    protein_id = data.get('protein_id', '').strip()
    if not protein_id:
        return jsonify({'error': 'protein_id required'}), 400
    run_id = str(uuid.uuid4())
    active_runs[run_id] = {
        'status': 'running', 'protein_id': protein_id,
        'steps': {}, 'results': None, 'error': None,
        'cancel': threading.Event(),
        'n_generate': int(data.get('n_generate', N_GENERATE)),
        'n_dock':     int(data.get('n_dock',     N_DOCK)),
    }
    socket_id = data.get('socket_id', '')
    if socket_id:
        _sid_to_run[socket_id] = run_id
    threading.Thread(
        target=run_pipeline_async,
        args=(run_id, protein_id,
              data.get('e3_ligase', 'CRBN'),
              data.get('cell_line', 'HEK293')),
        daemon=True,
    ).start()
    return jsonify({'run_id': run_id})


@app.get('/api/status/<run_id>')
def get_status(run_id):
    run = active_runs.get(run_id)
    if not run:
        return jsonify({'error': 'run not found'}), 404
    return jsonify({
        'status': run['status'], 'protein_id': run['protein_id'],
        'steps': run['steps'], 'error': run.get('error'),
    })


@app.get('/api/results/<run_id>')
def get_results(run_id):
    run = active_runs.get(run_id)
    if not run:
        return jsonify({'error': 'run not found'}), 404
    if run['status'] != 'complete':
        return jsonify({'error': 'not complete yet'}), 202
    return jsonify(run['results'])


@app.get('/api/fetch-structure')
def fetch_structure():
    id_str = request.args.get('id', '4OLI')
    try:
        pdb, residue_count, lysine_count, name, source = _resolve_protein(id_str)
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 404
    return jsonify({
        'id': id_str.upper(), 'name': name,
        'residue_count': residue_count, 'lysine_count': lysine_count,
        'source': source, 'pdb': pdb,
    })


# ---------------------------------------------------------------------------
# Experimental aptamers (PubMed search — informational only, not pipeline)
# ---------------------------------------------------------------------------

_KD_PATS = [
    re.compile(r'K[dD]\s*(?:of|=|~)?\s*([\d.]+)\s*(n[Mm]|nM|pM)', re.I),
    re.compile(r'dissociation constant[^\d]*([\d.]+)\s*(n[Mm]|pM)', re.I),
]
_SEQ_PAT    = re.compile(r'\b([ACGTU]{12,60})\b')
_PUBMED_URL = 'https://eutils.ncbi.nlm.nih.gov/entrez/eutils'


def _search_pubmed(query, max_results=8):
    try:
        r = requests.get(f'{_PUBMED_URL}/esearch.fcgi',
                         params={'db': 'pubmed', 'term': query,
                                 'retmax': max_results, 'retmode': 'json'}, timeout=10)
        if r.status_code == 200:
            return r.json().get('esearchresult', {}).get('idlist', [])
    except Exception:
        pass
    return []


def _fetch_abstracts(pmids):
    if not pmids:
        return []
    try:
        r = requests.get(f'{_PUBMED_URL}/efetch.fcgi',
                         params={'db': 'pubmed', 'id': ','.join(pmids),
                                 'rettype': 'xml', 'retmode': 'xml'}, timeout=15)
        if r.status_code != 200:
            return []
        root = ET.fromstring(r.text)
        out = []
        for art in root.findall('.//PubmedArticle'):
            pmid_el  = art.find('.//PMID')
            title_el = art.find('.//ArticleTitle')
            abs_els  = art.findall('.//AbstractText')
            year_el  = art.find('.//PubDate/Year')
            out.append({
                'pmid':     pmid_el.text  if pmid_el  else '',
                'title':    title_el.text if title_el else '',
                'abstract': ' '.join((el.text or '') for el in abs_els if el.text),
                'year':     year_el.text  if year_el  else '',
            })
        return out
    except Exception:
        return []


@app.get('/api/experimental-aptamers')
def experimental_aptamers():
    protein_id = request.args.get('id', '').strip()
    if not protein_id:
        return jsonify({'error': 'id required'}), 400
    pmids = _search_pubmed(
        f'({protein_id}[Title/Abstract]) AND (aptamer OR SELEX) AND RNA', 10)
    if len(pmids) < 3:
        pmids = list(set(pmids + _search_pubmed(f'{protein_id} aptamer SELEX', 8)))
    pubmed_apts = []
    for art in _fetch_abstracts(pmids[:10]):
        combined = art['title'] + ' ' + art['abstract']
        if not re.search(r'\baptamer\b', combined, re.I):
            continue
        m_kd  = next((p.search(combined) for p in _KD_PATS if p.search(combined)), None)
        m_seq = _SEQ_PAT.search(art['abstract'])
        seq   = m_seq.group(1).upper() if m_seq else None
        if seq and not set(seq).issubset({'A', 'U', 'G', 'C', 'T'}):
            seq = None
        pubmed_apts.append({
            'name':     art['title'][:60] + ('...' if len(art['title']) > 60 else ''),
            'protein_target': protein_id,
            'sequence': seq, 'length': len(seq) if seq else None,
            'kd':       f'{m_kd.group(1)} {m_kd.group(2)}' if m_kd else None,
            'year': art['year'], 'pmid': art['pmid'], 'title': art['title'],
            'selection_method': 'SELEX' if re.search(r'\bSELEX\b', combined) else 'reported',
            'source': 'pubmed',
        })
    return jsonify({'protein_id': protein_id, 'pubmed_hits': len(pmids),
                    'aptamers': pubmed_apts})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    socketio.run(app, debug=False, port=5000, allow_unsafe_werkzeug=True)
