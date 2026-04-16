# AptaDeg

AptaDeg is a computational pipeline and web application for designing RNA-based PROTACs (Proteolysis-Targeting Chimeras). It automates the end-to-end process of generating candidate RNA aptamers that recruit target proteins to E3 ubiquitin ligases for selective degradation.

The platform combines de novo RNA generation, 3D structure prediction, molecular docking, and multi-criteria scoring into a single integrated workflow, with real-time progress tracking through a browser interface.

## Pipeline

AptaDeg executes a 13-step automated pipeline:

| Step | Description |
|------|-------------|
| 0 | Load CRBN E3 ligase with pomalidomide reference geometry |
| 1 | Fetch target protein structure from RCSB PDB or predict via ESMFold |
| 2 | Clean structure (strip waters, heteroatoms, select relevant chains) |
| 3 | Detect binding pockets using fpocket |
| 4 | Search literature for known aptamers (PubMed, Aptagen, AptaBase) |
| 5 | Generate de novo RNA aptamer candidates via RNAFlow |
| 6 | Validate secondary structures with ViennaRNA |
| 7 | Predict 3D aptamer structures using rna-tools |
| 8 | Dock aptamers against target protein using rDock (parallelised) |
| 9 | Score candidates on epitope quality, lysine accessibility, ternary complex geometry, and hook effect |
| 10-12 | Three rounds of iterative refinement (mutate top candidates, re-dock, re-score) |

## Tech Stack

**Frontend:** React 18, Vite, Tailwind CSS, Framer Motion, Recharts, Nivo, 3Dmol.js, Socket.IO client

**Backend:** Flask, Flask-SocketIO, BioPython, NumPy, ViennaRNA, rna-tools, rDock (via WSL), fpocket

## Project Structure

```
aptadeg/
├── backend/
│   ├── app.py              # Flask server, REST + WebSocket API
│   ├── pipeline.py         # 13-step computational pipeline
│   ├── literature.py       # Parallel aptamer literature scraper
│   ├── run_rnaflow_wsl.py  # RNAFlow runner (WSL)
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── App.jsx         # Main app, phase-based routing
│   │   ├── views/          # Landing, Pipeline, Results screens
│   │   ├── components/     # UI components (3D viewer, cards, charts)
│   │   ├── hooks/          # usePipeline (SocketIO state management)
│   │   └── styles/         # Design tokens
│   ├── package.json
│   └── vite.config.js
└── start.bat               # Windows launcher (backend + frontend)
```

## Setup

### Prerequisites

- Python 3.10+
- Node.js 18+
- WSL with rDock installed (for molecular docking)
- RNAFlow checkpoint (optional, for de novo generation)
- ViennaRNA (optional, for folding validation)
- fpocket (optional, for pocket detection)

### Backend

```bash
cd backend
pip install -r requirements.txt
python app.py
```

The Flask server starts on port 5000.

### Frontend

```bash
cd frontend
npm install
npm run dev
```

The Vite dev server starts on port 3000 with a proxy to the backend.

### Quick Start (Windows)

```bash
start.bat
```

This launches both the backend and frontend in separate terminal windows.

## Usage

1. Open `http://localhost:3000` in a browser
2. Enter a PDB ID (e.g. `1YCR`) or UniProt accession for the target protein
3. Select an E3 ligase and cell line context
4. Click **Run Pipeline** to start the automated design process
5. Monitor real-time progress as each step completes
6. Review ranked candidates with docking scores, structural metrics, and interactive 3D visualisation

## How It Works

AptaDeg treats RNA PROTAC design as a computational optimisation problem. The pipeline generates diverse aptamer candidates through both literature mining and de novo generation, then evaluates each candidate across multiple biophysical criteria:

- **Epitope quality** -- Does the aptamer bind near surface-exposed lysine residues on the target?
- **Lysine accessibility** -- Are ubiquitination-competent lysines within reach of the E3 ligase?
- **Ternary complex geometry** -- Can the aptamer simultaneously engage the target and E3 ligase in a productive orientation?
- **Hook effect** -- Is the binding affinity balanced to avoid the hook effect (where excess binder inhibits ternary complex formation)?

Top candidates undergo three rounds of iterative refinement, where point mutations are introduced, structures are re-predicted, and docking is repeated to converge on optimal designs.

## API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/run` | POST | Start a pipeline run with target protein, E3 ligase, and parameters |
| `/api/results/<run_id>` | GET | Retrieve results for a completed run |

WebSocket events (via Socket.IO):
- `step_update` -- Real-time progress for each pipeline step
- `pipeline_complete` -- Final ranked candidates
- `pipeline_failed` -- Error details on failure
