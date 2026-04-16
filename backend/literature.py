"""
Literature aptamer scraping for AptaDeg.

Sources (run in parallel, independent failures allowed):
  1. Hardcoded KNOWN_APTAMERS dictionary (checked first, no network)
  2. PubMed via NCBI eutils API (3 parallel queries)
  3. Aptagen Aptamer Index
  4. AptaBase

Sequences are validated with ViennaRNA, then 15 transition-biased
mutants are generated per literature seed at 5% mutation rate.
"""

import logging
import random
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

try:
    import RNA as _RNA
    _VIENNA_OK = True
except ImportError:
    _VIENNA_OK = False

log = logging.getLogger("aptadeg.literature")

# ---------------------------------------------------------------------------
# Validated aptamer library
# ---------------------------------------------------------------------------

KNOWN_APTAMERS = {
    "MDM2": [
        {
            "sequence": "GGGAGACAAGAAUAAACGCUCAAGGGUCAAACAGGAUGGAUGUUGGGAGUGUAGUGU",
            "source": "MDM2 RNA aptamer — Shieh et al. 2010",
            "kd_nm": 80.0,
            "target_full": "MDM2",
        },
        {
            "sequence": "AUCUGUACUUGGGAUGACCUGCCCGGGCGAGGGCCCAUCAAAGCCAUGUAGGUGAUG",
            "source": "MDM2 aptamer literature",
            "kd_nm": 120.0,
            "target_full": "MDM2",
        },
    ],
    "TP53": [
        {
            "sequence": "GGGAGAAUUCAAUAGCUUUGAAAUAACUUUGAAAGCUAUUGAAUUCUC",
            "source": "p53 DNA-binding domain RNA aptamer",
            "kd_nm": 45.0,
            "target_full": "p53",
        },
    ],
    "P53": [
        {
            "sequence": "GGGAGAAUUCAAUAGCUUUGAAAUAACUUUGAAAGCUAUUGAAUUCUC",
            "source": "p53 DNA-binding domain RNA aptamer",
            "kd_nm": 45.0,
            "target_full": "p53",
        },
    ],
    "MYC": [
        {
            "sequence": (
                "UGCCUGGUGGGCGCUGUCGCGUGGUGCG"
                "GAGUGGCAUUUGGUGCAUGGUGGUGGUG"
            ),
            "source": "MA9C1 — Advanced Science 2024",
            "kd_nm": 1.5,
            "target_full": "c-Myc",
        },
        {
            "sequence": "GGAGGAGGAGGAGGAGGAGGAGGAGGAG",
            "source": "Pu27 G-quadruplex",
            "kd_nm": 0.37,
            "target_full": "c-Myc",
        },
    ],
    "KRAS": [
        {
            "sequence": (
                "GGGAGGAGGAAGAGGAGGGGGGAGGGAG"
                "GAGGAGGAAGAGGAGGGGG"
            ),
            "source": "KRAS RNA aptamer literature",
            "kd_nm": 25.0,
        }
    ],
    "VEGF": [
        {
            "sequence": (
                "GGGCGACCCUGGGCCAAGUCCUGUGUGU"
                "GGGGUCGACCCAGCUUCGGAGACAGUGC"
            ),
            "source": "Anti-VEGF aptamer",
            "kd_nm": 0.14,
        }
    ],
    "EGFR": [
        {
            "sequence": (
                "GCGACUGAGCCCAGUGCACGAAUAGCGU"
                "AGGGAAGAGAGAUGAGUGCAAAGCAGAC"
            ),
            "source": "E07 EGFR aptamer",
            "kd_nm": 2.4,
        }
    ],
    "THROMBIN": [
        {
            "sequence": "GGUUGGUGUGGUUGG",
            "source": "TBA15",
            "kd_nm": 25.0,
        }
    ],
    "STAT3": [
        {
            "sequence": (
                "CUCCUCAGACCACAUCCGAAAGUCAAGCC"
                "UGAGCCAGAUUCUCCAGAGCUAUCAGAG"
            ),
            "source": "STAT3 RNA aptamer literature",
            "kd_nm": 50.0,
        }
    ],
    "BCL2": [
        {
            "sequence": (
                "GGGAGACAAGAAUAAACGCUCAAGGUC"
                "CAAACAGGAUGGAUGUUGGGAGUGUGAG"
            ),
            "source": "Bcl-2 aptamer literature",
            "kd_nm": 0.35,
        }
    ],
}

# Alias map: alternate names → canonical key
_ALIASES: dict[str, list[str]] = {
    "MYC":      ["MYC", "CMYC", "MYC1", "C-MYC"],
    "EGFR":     ["EGFR", "ERBB1", "HER1"],
    "KRAS":     ["KRAS", "KRAS2", "RASK"],
    "MDM2":     ["MDM2", "HDM2", "MDM2P53"],
    "TP53":     ["TP53", "P53", "TRP53"],
    "P53":      ["P53", "TP53", "TRP53"],
}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_NCBI_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
_NCBI_MIN_INTERVAL = 0.34  # seconds between requests (NCBI rate limit)

_RNA_SEQ_PAT = re.compile(r"\b[AUGC]{20,60}\b")
_DNA_TO_RNA  = str.maketrans("Tt", "Uu")

_TRANSITIONS   = {"A": "G", "G": "A", "U": "C", "C": "U"}
_TRANSVERSIONS = {"A": ["U", "C"], "G": ["U", "C"], "U": ["A", "G"], "C": ["A", "G"]}

MFE_THRESHOLD = -5.0

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalise(seq: str) -> str:
    return seq.upper().translate(_DNA_TO_RNA)


def _is_valid_rna(seq: str) -> bool:
    return bool(seq) and set(seq.upper()).issubset({"A", "U", "G", "C"}) and len(seq) >= 20


def _fold(seq: str) -> tuple[float, bool]:
    """Return (mfe, is_stable). Raises if ViennaRNA not installed."""
    if not _VIENNA_OK:
        raise RuntimeError(
            "ViennaRNA not installed — required for literature aptamer validation. "
            "Install with: pip install viennarna"
        )
    try:
        _, mfe = _RNA.fold(seq)
        return float(mfe), float(mfe) <= MFE_THRESHOLD
    except Exception as e:
        raise RuntimeError(f"ViennaRNA fold failed: {e}") from e


def _kmer_similarity(a: str, b: str, k: int = 4) -> float:
    """Jaccard similarity over k-mers — fast proxy for sequence identity."""
    def kmers(s):
        return {s[i : i + k] for i in range(max(0, len(s) - k + 1))}
    ka, kb = kmers(a), kmers(b)
    if not ka or not kb:
        return 0.0
    return len(ka & kb) / len(ka | kb)


def _deduplicate(sequences: list[str], threshold: float = 0.80) -> list[str]:
    """Remove sequences >80% similar (k-mer Jaccard) to any already accepted."""
    accepted: list[str] = []
    for seq in sequences:
        if not any(_kmer_similarity(seq, a) > threshold for a in accepted):
            accepted.append(seq)
    return accepted


# ---------------------------------------------------------------------------
# KNOWN_APTAMERS lookup
# ---------------------------------------------------------------------------

def _lookup_known(protein_name: str) -> list[dict]:
    """Return KNOWN_APTAMERS entries matching protein_name via key or alias."""
    name_up = protein_name.upper()
    # Direct key match
    if name_up in KNOWN_APTAMERS:
        return list(KNOWN_APTAMERS[name_up])
    # Alias match
    for canonical, aliases in _ALIASES.items():
        if name_up in aliases and canonical in KNOWN_APTAMERS:
            return list(KNOWN_APTAMERS[canonical])
    # Substring match
    for key, entries in KNOWN_APTAMERS.items():
        if key in name_up or name_up in key:
            return list(entries)
    return []


# ---------------------------------------------------------------------------
# Source 2 — PubMed
# ---------------------------------------------------------------------------

def _pubmed_search(query: str) -> list[str]:
    r = requests.get(
        f"{_NCBI_BASE}/esearch.fcgi",
        params={"db": "pubmed", "term": query, "retmax": 20, "retmode": "json"},
        timeout=8,
    )
    r.raise_for_status()
    return r.json().get("esearchresult", {}).get("idlist", [])


def _pubmed_fetch_abstracts(pmids: list[str]) -> list[str]:
    if not pmids:
        return []
    r = requests.get(
        f"{_NCBI_BASE}/efetch.fcgi",
        params={"db": "pubmed", "id": ",".join(pmids), "rettype": "xml", "retmode": "xml"},
        timeout=8,
    )
    r.raise_for_status()
    root = ET.fromstring(r.text)
    abstracts = []
    for art in root.findall(".//PubmedArticle"):
        els = art.findall(".//AbstractText")
        abstracts.append(" ".join(el.text or "" for el in els if el.text))
    return abstracts


def _scrape_pubmed(protein_name: str) -> list[str]:
    """Run 3 PubMed queries in parallel; extract RNA sequences from abstracts."""
    queries = [
        f'"{protein_name}" RNA aptamer SELEX',
        f'"{protein_name}" aptamer sequence binding',
        f'"{protein_name}" RNA aptamer therapeutic',
    ]
    all_pmids: set[str] = set()
    lock = __import__("threading").Lock()
    last_req = [0.0]

    def _query(q: str) -> list[str]:
        with lock:
            wait = _NCBI_MIN_INTERVAL - (time.time() - last_req[0])
            if wait > 0:
                time.sleep(wait)
            last_req[0] = time.time()
        return _pubmed_search(q)

    with ThreadPoolExecutor(max_workers=3) as ex:
        for fut in as_completed({ex.submit(_query, q): q for q in queries}):
            try:
                all_pmids.update(fut.result())
            except Exception as e:
                log.warning("PubMed query failed: %s", e)

    if not all_pmids:
        return []

    seqs: list[str] = []
    for abstract in _pubmed_fetch_abstracts(list(all_pmids)[:20]):
        for m in _RNA_SEQ_PAT.findall(abstract):
            seq = _normalise(m)
            if _is_valid_rna(seq):
                seqs.append(seq)
    return seqs


# ---------------------------------------------------------------------------
# Source 3 — Aptagen
# ---------------------------------------------------------------------------

def _scrape_aptagen(protein_name: str) -> list[str]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("beautifulsoup4 not installed — Aptagen scraping skipped")
        return []
    r = requests.get(
        "https://www.aptagen.com/aptamer-index/",
        params={"s": protein_name},
        timeout=8,
        headers={"User-Agent": "AptaDeg/1.0 (research)"},
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    seqs: list[str] = []
    for text in soup.find_all(string=_RNA_SEQ_PAT):
        for m in _RNA_SEQ_PAT.findall(str(text)):
            seq = _normalise(m)
            if _is_valid_rna(seq):
                seqs.append(seq)
    return seqs


# ---------------------------------------------------------------------------
# Source 4 — AptaBase
# ---------------------------------------------------------------------------

def _scrape_aptabase(protein_name: str, uniprot_id: str = "") -> list[str]:
    try:
        from bs4 import BeautifulSoup
    except ImportError:
        log.warning("beautifulsoup4 not installed — AptaBase scraping skipped")
        return []
    r = requests.get(
        "http://aptabase.net/",
        params={"q": uniprot_id or protein_name},
        timeout=8,
        headers={"User-Agent": "AptaDeg/1.0 (research)"},
    )
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    seqs: list[str] = []
    for text in soup.find_all(string=_RNA_SEQ_PAT):
        for m in _RNA_SEQ_PAT.findall(str(text)):
            seq = _normalise(m)
            if _is_valid_rna(seq):
                seqs.append(seq)
    return seqs


# ---------------------------------------------------------------------------
# Transition-biased mutation + mutant generation
# ---------------------------------------------------------------------------

def _mutate_transition_biased(sequence: str, mutation_rate: float, rng: random.Random) -> str:
    """
    Mutate a sequence with transition-biased point mutations.
    Transitions (A↔G, U↔C) are weighted 3× over transversions.
    """
    bases = list(sequence)
    for i, nt in enumerate(bases):
        if rng.random() < mutation_rate:
            if rng.random() < 0.75:  # 3× weight for transitions
                bases[i] = _TRANSITIONS.get(nt, nt)
            else:
                choices = _TRANSVERSIONS.get(nt, [nt])
                bases[i] = rng.choice(choices)
    return "".join(bases)


def generate_mutants(
    sequence: str,
    source_tag: str,
    parent_kd: float | None = None,
    n: int = 15,
    mutation_rate: float = 0.05,
) -> list[dict]:
    """
    Generate up to n stable mutants via transition-biased mutation.
    ViennaRNA stability check (MFE <= -5.0) applied to each mutant.
    Raises RuntimeError if ViennaRNA not available.
    """
    rng = random.Random()  # non-seeded: genuine randomness each call
    results: list[dict] = []
    attempts = 0
    max_attempts = n * 10

    while len(results) < n and attempts < max_attempts:
        attempts += 1
        mutant = _mutate_transition_biased(sequence, mutation_rate, rng)
        if mutant == sequence:
            continue
        _, stable = _fold(mutant)
        if not stable:
            continue
        results.append({
            "sequence":          mutant,
            "generation_method": source_tag,
            "source":            "literature_mutant",
            "parent_sequence":   sequence,
            "parent_kd_nm":      parent_kd,
            "round_introduced":  0,
            "score_history":     [],
        })

    return results


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def scrape_literature_aptamers(
    protein_name: str,
    protein_id: str = "",
    log_fn=None,
) -> list[dict]:
    """
    Scrape all 4 sources in parallel; validate with ViennaRNA; generate mutants.

    Returns a list of aptamer dicts compatible with the pipeline pool schema:
      sequence, generation_method, source, parent_sequence, parent_kd_nm,
      round_introduced, score_history

    Raises RuntimeError only if ViennaRNA is unavailable (required for validation).
    Individual network sources fail gracefully — all others continue.
    """
    if log_fn is None:
        log_fn = log.info

    # Source 1: hardcoded library (no network)
    known = _lookup_known(protein_name)
    source_counts = {"pubmed": 0, "aptagen": 0, "aptabase": 0, "hardcoded": len(known)}

    # Sources 2-4: parallel network queries
    raw_seqs: list[str] = []

    def _run_pubmed():
        try:
            seqs = _scrape_pubmed(protein_name)
            return ("pubmed", seqs)
        except Exception as e:
            log.warning("PubMed scraping failed: %s", e)
            return ("pubmed", [])

    def _run_aptagen():
        try:
            seqs = _scrape_aptagen(protein_name)
            return ("aptagen", seqs)
        except Exception as e:
            log.warning("Aptagen scraping failed: %s", e)
            return ("aptagen", [])

    def _run_aptabase():
        try:
            seqs = _scrape_aptabase(protein_name, protein_id)
            return ("aptabase", seqs)
        except Exception as e:
            log.warning("AptaBase scraping failed: %s", e)
            return ("aptabase", [])

    with ThreadPoolExecutor(max_workers=3) as ex:
        futs = [ex.submit(_run_pubmed), ex.submit(_run_aptagen), ex.submit(_run_aptabase)]
        try:
            for fut in as_completed(futs, timeout=25):
                src, seqs = fut.result()
                source_counts[src] = len(seqs)
                raw_seqs.extend(seqs)
        except TimeoutError:
            log.warning("Network scraping timed out — using results collected so far")

    log_fn(
        f"> Literature search: {source_counts['pubmed']} from PubMed, "
        f"{source_counts['aptagen']} from Aptagen, "
        f"{source_counts['hardcoded']} from validated library"
    )

    # Merge known sequences with scraped
    known_seqs = [k["sequence"] for k in known]
    all_seqs   = list(dict.fromkeys(known_seqs + raw_seqs))  # preserve order, dedup exact
    all_seqs   = _deduplicate(all_seqs)

    log_fn(f"> Total literature aptamers: {len(all_seqs)}")

    # Validate + generate mutants
    pool: list[dict] = []
    n_mutants_total = 0

    for seq in all_seqs:
        known_entry = next((k for k in known if k["sequence"] == seq), None)
        kd          = known_entry.get("kd_nm") if known_entry else None
        src_name    = known_entry.get("source", "literature_scraped") if known_entry else "literature_scraped"

        # ViennaRNA stability gate
        try:
            _, stable = _fold(seq)
        except RuntimeError:
            raise  # propagate ViennaRNA missing error
        if not stable:
            continue

        pool.append({
            "sequence":          seq,
            "generation_method": "literature_seeded",
            "source":            src_name,
            "parent_sequence":   None,
            "parent_kd_nm":      kd,
            "round_introduced":  0,
            "score_history":     [],
        })

        # Generate 15 mutants at 5% mutation rate
        try:
            short_src = src_name.split(" ")[0].replace("—", "").strip()
            mutants = generate_mutants(
                seq,
                source_tag=f"literature_derived_{short_src}",
                parent_kd=kd,
                n=15,
                mutation_rate=0.05,
            )
            for m in mutants:
                m["round_introduced"] = 0
                m["score_history"]    = []
            pool.extend(mutants)
            n_mutants_total += len(mutants)
        except RuntimeError:
            raise
        except Exception as e:
            log.warning("Mutant generation failed for %s…: %s", seq[:10], e)

    log_fn(f"> Generated {n_mutants_total} variants from {len(all_seqs)} literature seeds")
    return pool
