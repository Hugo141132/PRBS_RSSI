# RSSI-based Secret Key Generation (SKG) Research

This repository provides Python project scaffolding for Received Signal Strength Indicator (RSSI)-based Secret Key Generation (SKG) research.

> **Progress Handoff Document**: See [docs/progress.md](docs/progress.md) for a self-contained summary of project status, filtering and correlation validation results, and reproduction instructions.

---

## Directory Structure & Folder Responsibilities

```text
PRBS_RSSI/
├── data/
│   └── raw/
│       ├── dummy/                    # Dummy dataset for software validation
│       │   ├── Dummy RSSI (data Indoor).xlsx
│       │   └── README.md
│       └── measured/                 # Reserved for empirical physical channel probing measurement data
│           └── README.md
├── docs/                             # Methodological notes, equation references, and handoff documents
│   ├── methodology.md
│   └── progress.md
├── outputs/                          # Calculation artifacts, plots, and run results (ignored by Git via .gitignore)
│   └── .gitkeep
├── src/
│   └── rssi_skg/                     # Main Python source package modules (loader, filter, correlation, plotting, cli)
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── correlation.py
│       ├── filter.py
│       ├── loader.py
│       └── plotting.py
├── tests/                            # Unit tests and software validation
│   ├── __init__.py
│   ├── test_correlation.py
│   ├── test_filter.py
│   ├── test_loader.py
│   └── test_plotting.py
├── .gitignore                        # Ignore rules for cache files, venv, and outputs
├── PA.pdf                            # Primary methodological reference document
├── pyproject.toml                    # Minimal Python project metadata (PEP 517/621)
└── README.md                         # Main project documentation
```

### Responsibility Breakdown
- `src/rssi_skg/`: Python library code for the SKG pipeline:
  - `loader.py`: Excel workbook loading and row/column integrity validation.
  - `filter.py`: Scalar Modified Sage–Husa Adaptive Kalman Filter (MSHKF) implementation (`PA.pdf` Section 3.2.2).
  - `correlation.py`: Zero-lag Pearson correlation coefficient computation (`PA.pdf` Equation 3.62).
  - `plotting.py`: Aggregate bubble scatter visualization and pre-/post-filtering comparison plots.
  - `cli.py`: Unified CLI supporting pure correlation mode (default) and optional filtering mode.
- `tests/`: Automated unit tests ensuring algorithmic correctness, channel isolation, numerical safeguards, and regression testing (`test_correlation.py`, `test_filter.py`, `test_loader.py`, `test_plotting.py`).
- `data/raw/dummy/`: Dummy dataset for software validation. Contains `Dummy RSSI (data Indoor).xlsx` and local `README.md`.
- `data/raw/measured/`: Reserved folder for real wireless channel measurement data (empirical physical channel probing).
- `outputs/`: Stores calculation outputs, visual artifacts, and reports. Excluded from Git tracking except for `.gitkeep`.
- `docs/`: Technical documentation, mathematical equation literature references, research decision log (`methodology.md`), and progress handoff summary ([docs/progress.md](docs/progress.md)).

---

## Dummy Data Provenance & Definition

- **File Source**: `Dummy RSSI (data Indoor).xlsx` (500 sample rows).
- **Column Semantics**:
  - `Alice`: RSSI values received by Alice from Bob's transmission.
  - `Bob`: RSSI values received by Bob from Alice's transmission.
  - `Eve1-Alice`: RSSI values intercepted and received by a third party (Eve) from Alice's transmission signal.
  - `Eve1-Bob`: RSSI values intercepted and received by a third party (Eve) from Bob's transmission signal.
- **Scope & Function**:
  This dummy dataset is used strictly for **software validation** (validating functional workflows, data parsing, and algorithmic computational correctness), **not** for making empirical claims or theoretical conclusions regarding real wireless propagation channels.
- **Channel Probing Status**:
  Empirical physical channel probing is currently postponed, not replaced. Real channel measurements will be conducted in a subsequent hardware testing phase.

---

## RSSI Filtering Stage Implementation (Modified Sage–Husa AKF)

- **Methodological Reference**: Governed by `PA.pdf`, **Section 3.2.2, Equations (3.10)–(3.20), pages 26–27**:
  - **Scalar RSSI Modeling Assumptions**:
    - State transition matrix $\Phi = 1.0$ (static/slowly varying channel RSSI model: $X_k = X_{k-1} + q_{k-1} + w_{k-1}$).
    - Measurement matrix $H = 1.0$ (direct scalar RSSI observation in dBm: $Z_k = X_k + r_k + v_k$).
  - **Noise Adaptation Mode**:
    - The fixed scalar process-noise covariance $Q$ is held constant at $0.1\ \text{dBm}^2$.
    - The adaptive measurement-noise covariance $\hat{R}_k$ is estimated online via Equation (3.15).
    - The noise means $q$ and $r$ ($\hat{q}_k$ and $\hat{r}_k$) are recursively updated via Equations (3.19) and (3.13).
  - **Rationale for Omitting Adaptive $Q$ Update (Equation 3.20)**:
    This implementation specifically follows the modeling assumption stated in the final paragraph of `PA.pdf` Section 3.2.2 (page 27), where the process-noise covariance $Q$ is assumed to be known and held fixed (*known prior*). Consequently, the measurement-noise covariance $\hat{R}_k$ is adaptively estimated online and the adaptive $Q$ update in Equation (3.20) is not executed.

### Preserved Calculation Sequence (Equations 3.10–3.19)

**a. Adaptive weight (Equation 3.10)**

$$
D_k = \frac{D_{k-1}}{D_{k-1} + b}, \qquad D_0 = 1
$$

**b. State prediction (Equation 3.11)**

$$
\hat{X}(k|k-1) = \Phi \hat{X}_{k-1} + \hat{q}_{k-1}
$$

**c. Error covariance prediction (Equation 3.12)**

$$
P(k|k-1) = \Phi P_{k-1} \Phi^T + Q
$$

**d. Measurement noise mean update (Equation 3.13)**

$$
\hat{r}_k = (1 - D_k)\hat{r}_{k-1} + D_k \left(Z_k - H \hat{X}(k|k-1)\right)
$$

**e. Innovation calculation using updated $\hat{r}_k$ (Equation 3.14)**

$$
e_k = Z_k - H \hat{X}(k|k-1) - \hat{r}_k
$$

**f. Measurement noise covariance update (Equation 3.15)**

$$
\hat{R}_k = (1 - D_k)\hat{R}_{k-1} + D_k e_k^2
$$

**g. Kalman gain (Equation 3.16)**

$$
K_k = \frac{P(k|k-1) H^T}{H P(k|k-1) H^T + \hat{R}_k}
$$

**h. State update (Equation 3.17)**

$$
\hat{X}_k = \hat{X}(k|k-1) + K_k e_k
$$

**i. Error covariance update (Equation 3.18)**

$$
P_k = (1 - K_k H) P(k|k-1)
$$

**j. Process noise mean update (Equation 3.19)**

$$
\hat{q}_k = (1 - D_k)\hat{q}_{k-1} + D_k \left(\hat{X}_k - \Phi \hat{X}_{k-1}\right)
$$

### Configuration Parameters, Units & Rationale

| Parameter | Default Value | Units | Specification Status | Rationale |
| :--- | :--- | :--- | :--- | :--- |
| $b$ | `0.99` | Dimensionless | Selected Value within Literature Range | Selected value within the literature range stated in `PA.pdf` Section 3.2.2 ($0.95 \le b \le 0.999$), not a single prescriptively mandated value. Yields an effective memory horizon of $\approx 100$ samples. |
| $D_0$ | `1.0` | Dimensionless | Explicit (`PA.pdf` Eq. 3.10) | Initial adaptive weight at step $k=0$. |
| $\Phi$ | `1.0` | Dimensionless | Modeling Assumption | Slowly varying wireless channel state transition assumption. |
| $H$ | `1.0` | Dimensionless | Modeling Assumption | Direct observation matrix for scalar RSSI signals. |
| $x_0$ | Auto (`z[0]`) | $\text{dBm}$ | Implementation Assumption | Initializes initial state from the channel's first sample to eliminate transient bias. |
| $P_0$ | `1.0` | $\text{dBm}^2$ | Software Validation Assumption | Uncalibrated software-validation assumption for initial error covariance, not a measured physical transceiver/channel property. |
| $q_0$ | `0.0` | $\text{dBm}$ | Implementation Assumption | Initial process noise mean (assuming no initial systematic drift). |
| $r_0$ | `0.0` | $\text{dBm}$ | Implementation Assumption | Initial measurement noise mean (assuming no initial bias). |
| $Q$ | `0.1` | $\text{dBm}^2$ | Software Validation Assumption | Uncalibrated software-validation assumption for fixed process-noise covariance, not a measured physical transceiver/channel property. Following `PA.pdf` Section 3.2.2, $Q$ is assumed to be a known prior. |
| $R_0$ | `1.0` | $\text{dBm}^2$ | Software Validation Assumption | Uncalibrated software-validation assumption for initial measurement-noise covariance, not a measured physical transceiver/channel property. |

### Sample Indexing Policy
To prevent double-counting of the first observation:
- When $x_0$ is automatically initialized from the first observation ($x_0 = z_0$), the sample $z_0$ is assigned directly as the state at time index 0 ($\hat{X}_0 = z_0$). The recursive update loop of Equations (3.10)–(3.19) starts from measurement $z_1$ at step $k=1$. Thus, $z_0$ is used exactly once as the initial condition and **is never re-fed as a measurement innovation input**.
- If a prior $x_0$ is explicitly supplied externally, all measurements $z_0, \dots, z_{N-1}$ are processed through steps $k = 1, \dots, N$.

### Channel Isolation & Numerical Safeguards
- **Channel Isolation**: The Alice, Bob, Eve1-Alice, and Eve1-Bob channels are filtered using separate, independent filter instances. No state is shared across channels.
- **Finite-Value Validation**: Enforces `math.isfinite` across all input samples; explicitly rejects `NaN`, `+Inf`, and `-Inf`.
- **Covariance Safeguards**: Enforces $\hat{R}_k \ge R_{\min} = 10^{-8}\ \text{dBm}^2$, $P_k \ge 0.0$, validates that the Kalman gain denominator is strictly non-singular ($P_{\text{pred}} + \hat{R}_k > 0$), and raises a `FloatingPointError` if significant negative covariance or non-finite values occur (never silently masked).

---

## Correlation Stage Implementation (Pearson Correlation)

- **Methodological Reference**: Governed by `PA.pdf`, **Equation (3.62), page 34**:

$$
\rho_{u,v} =
\frac{
\sum_{n=1}^{N}
\left(X_u(n)-\mu_u\right)
\left(X_v(n)-\mu_v\right)
}{
\sqrt{\sum_{n=1}^{N}\left(X_u(n)-\mu_u\right)^2}
\sqrt{\sum_{n=1}^{N}\left(X_v(n)-\mu_v\right)^2}
}
$$

Where:
- $X_u(n)$: RSSI sample value on channel $u$ at observation index $n$.
- $X_v(n)$: RSSI sample value on channel $v$ at observation index $n$.
- $\mu_u$: Sample mean of channel $u$ RSSI over $N$ observations ($\mu_u = \frac{1}{N}\sum_{n=1}^N X_u(n)$).
- $\mu_v$: Sample mean of channel $v$ RSSI over $N$ observations ($\mu_v = \frac{1}{N}\sum_{n=1}^N X_v(n)$).
- $N$: Total number of paired observations ($N = 500$ in the dummy validation dataset).
*(Note: Notations $u, v$ are mathematically equivalent to earlier $X, Y$ notations).*
- **Analysis Nature**: Pearson correlation is computed at zero lag.
- **Evaluated Channel Pairs**:
  1. `Alice–Bob`: Reciprocity estimate between legitimate communication partners ($u = \text{Alice}, v = \text{Bob}$).
  2. `Alice–Eve1-Alice`: Correlation between Alice's transmission and Eve's eavesdropping ($u = \text{Alice}, v = \text{Eve1-Alice}$).
  3. `Bob–Eve1-Bob`: Correlation between Bob's transmission and Eve's eavesdropping ($u = \text{Bob}, v = \text{Eve1-Bob}$).

### Pre- vs. Post-Filtering Correlation Results ($N=500$, `data_kind=dummy`)

| Channel Pair | Raw Correlation ($\rho_{\text{raw}}$) | Filtered Correlation ($\rho_{\text{filt}}$) | Change ($\Delta\rho$) |
| :--- | :--- | :--- | :--- |
| `Alice–Bob` | `+0.632263` | `+0.842244` | `+0.209981` |
| `Alice–Eve1-Alice` | `+0.017060` | `-0.013725` | `-0.030784` |
| `Bob–Eve1-Bob` | `+0.119310` | `+0.015151` | `-0.104159` |

*(Note: MSHKF filtering enhances legitimate reciprocal correlation for Alice–Bob while suppressing eavesdropper Eve's channel correlation toward zero on the software-validation dummy dataset).*

---

<a id="petunjuk-penyiapan-lingkungan--eksekusi"></a>
## Environment Setup & Execution Instructions

Execution commands from the repository root on Windows PowerShell using the direct Python binary `.\.venv\Scripts\python.exe`:

### 1. Local Virtual Environment Initialization (.venv)
```powershell
# Create local virtual environment
python -m venv .venv

# (Optional) Activate virtual environment in PowerShell
.\.venv\Scripts\Activate.ps1

# Install project and all development dependencies in editable mode
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 2. Running Unit Tests
The test suite comprises 31 automated tests (step-by-step intermediate numerical validation of independent MSHKF equations, channel isolation, sample indexing, numerical safeguards, Pearson correlation, workbook loading, and visualization generation):

```powershell
# Run all unit tests (31 tests)
.\.venv\Scripts\python.exe -m pytest -v
```

### 3. Running Analysis via CLI

#### A. Default Correlation Execution (Without Filtering - 100% Backward-Compatible)
```powershell
.\.venv\Scripts\python.exe -m rssi_skg -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" -o "outputs/dummy_rssi_correlation.csv" --figure-prefix "outputs/dummy_rssi_correlation"
```

#### B. Full Execution with MSHKF Filtering Stage
Run the CLI with the `--filter` flag along with unified artifact export options:
```powershell
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --filtered-samples-output "outputs/dummy_rssi_filtered_samples.csv" `
  --filter-config-output "outputs/dummy_rssi_filter_config.json" `
  --figure-prefix "outputs/dummy_rssi_filtered"
```

### 4. Output File Locations (`outputs/`)
All generated artifacts are stored in the `outputs/` directory (ignored by Git via `.gitignore`, except `.gitkeep`):
- `outputs/dummy_rssi_correlation.csv`: Raw correlation coefficients table for all three channel pairs ($N=500$).
- `outputs/dummy_rssi_correlation.png` / `.pdf`: Raw correlation visualization charts (horizontal bar + bubble scatter).
- `outputs/dummy_rssi_filtered_correlation.csv`: Comparative table of raw vs. filtered correlation coefficients along with $\Delta\rho$.
- `outputs/dummy_rssi_filtered_samples.csv`: Time-aligned row-by-row raw and filtered observation samples across all 4 channels.
- `outputs/dummy_rssi_filter_config.json`: Complete MSHKF configuration metadata, modeling assumptions, units, and rationale.
- `outputs/dummy_rssi_filtered.png`: High-resolution (300 dpi) comparative visualization featuring horizontal bar comparison, time-series smoothing trajectories, and 3 filtered bubble scatter panels.
- `outputs/dummy_rssi_filtered.pdf`: Comparative visualization in vector PDF format.

---

## Methodological Limitations & Warnings

The results of this analysis are strictly for **software validation** using synthetic dummy data. The resulting correlation coefficients **must not be used to draw empirical security conclusions or characterize real physical channel propagation**, as physical channel probing is postponed, not replaced.
