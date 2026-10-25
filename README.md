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
│   └── rssi_skg/                     # Main Python source package modules (loader, filter, correlation, plotting, quantization, cli)
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── correlation.py
│       ├── filter.py
│       ├── loader.py
│       ├── plotting.py
│       └── quantization.py
├── tests/                            # Unit tests and software validation
│   ├── __init__.py
│   ├── test_correlation.py
│   ├── test_filter.py
│   ├── test_loader.py
│   ├── test_plotting.py
│   └── test_quantization.py
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
  - `quantization.py`: Modified Adaptive Dual-Threshold Quantization (MADQ) engine, dual Gray 2-bit and 4-bit bitstream generation, and KAR calculation (`PA.pdf` Section 3.2.3 and Eq 3.64).
  - `plotting.py`: Aggregate bubble scatter visualization and pre-/post-filtering comparison plots.
  - `cli.py`: Unified CLI supporting pure correlation mode (default), optional filtering mode, and optional quantization mode.
- `tests/`: Automated unit tests ensuring algorithmic correctness, channel isolation, numerical safeguards, exact boundary conditions, encodings, and regression testing (`test_correlation.py`, `test_filter.py`, `test_loader.py`, `test_plotting.py`, `test_quantization.py`).
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
    - The fixed scalar process-noise covariance Q is held constant at 0.1 (dBm)².
    - The adaptive measurement-noise covariance $\hat{R}_k$ is estimated online via Equation (3.15).
    - The noise means q and r ($\hat{q}_k$ and $\hat{r}_k$) are recursively updated via Equations (3.19) and (3.13).
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
| $b$ | `0.99` | Dimensionless | Selected Value within Literature Range | Selected value within the literature range stated in `PA.pdf` Section 3.2.2 (0.95 ≤ b ≤ 0.999), not a single prescriptively mandated value. Yields an effective memory horizon of ≈ 100 samples. |
| $D_0$ | `1.0` | Dimensionless | Explicit (`PA.pdf` Eq. 3.10) | Initial adaptive weight at step k = 0. |
| $\Phi$ | `1.0` | Dimensionless | Modeling Assumption | Slowly varying wireless channel state transition assumption. |
| $H$ | `1.0` | Dimensionless | Modeling Assumption | Direct observation matrix for scalar RSSI signals. |
| $x_0$ | Auto (`z[0]`) | dBm | Implementation Assumption | Initializes initial state from the channel's first sample to eliminate transient bias. |
| $P_0$ | `1.0` | (dBm)² | Software Validation Assumption | Uncalibrated software-validation assumption for initial error covariance, not a measured physical transceiver/channel property. |
| $q_0$ | `0.0` | dBm | Implementation Assumption | Initial process noise mean (assuming no initial systematic drift). |
| $r_0$ | `0.0` | dBm | Implementation Assumption | Initial measurement noise mean (assuming no initial bias). |
| $Q$ | `0.1` | (dBm)² | Software Validation Assumption | Uncalibrated software-validation assumption for fixed process-noise covariance, not a measured physical transceiver/channel property. Following `PA.pdf` Section 3.2.2, Q is assumed to be a known prior. |
| $R_0$ | `1.0` | (dBm)² | Software Validation Assumption | Uncalibrated software-validation assumption for initial measurement-noise covariance, not a measured physical transceiver/channel property. |

### Sample Indexing Policy
To prevent double-counting of the first observation:
- When $x_0$ is automatically initialized from the first observation ($x_0 = z_0$), the sample $z_0$ is assigned directly as the state at time index 0 ($\hat{X}_0 = z_0$). The recursive update loop of Equations (3.10)–(3.19) starts from measurement $z_1$ at step $k=1$. Thus, $z_0$ is used exactly once as the initial condition and **is never re-fed as a measurement innovation input**.
- If a prior $x_0$ is explicitly supplied externally, all measurements $z_0, \dots, z_{N-1}$ are processed through steps $k = 1, \dots, N$.

### Channel Isolation & Numerical Safeguards
- **Channel Isolation**: The Alice, Bob, Eve1-Alice, and Eve1-Bob channels are filtered using separate, independent filter instances. No state is shared across channels.
- **Finite-Value Validation**: Enforces `math.isfinite` across all input samples; explicitly rejects `NaN`, `+Inf`, and `-Inf`.
- **Covariance Safeguards**: Enforces non-negative error covariance ($P_k \ge 0.0$), validates that the Kalman gain denominator is strictly non-singular ($P(k|k-1) + \hat{R}_k > 0$), and raises `FloatingPointError` if significant negative covariance or non-finite values occur (never silently masked).

The measurement-noise covariance lower-bound constraint is enforced at each step:

$$
\hat{R}_k \ge R_{\min} = 10^{-8}\,(\mathrm{dBm})^2
$$

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
- $\mu_u$: Sample mean of channel $u$ RSSI over $N$ observations.
- $\mu_v$: Sample mean of channel $v$ RSSI over $N$ observations.
- $N$: Total number of paired observations (N = 500 in the dummy validation dataset).

Sample mean of channel $u$:

$$
\mu_u = \frac{1}{N}\sum_{n=1}^{N} X_u(n)
$$

Sample mean of channel $v$:

$$
\mu_v = \frac{1}{N}\sum_{n=1}^{N} X_v(n)
$$

*(Note: The channel labels u and v correspond to the earlier X and Y notation).*
- **Analysis Nature**: Pearson correlation is computed at zero lag.
- **Evaluated Channel Pairs**:
  1. `Alice–Bob`: Reciprocity estimate between legitimate communication partners (u = Alice, v = Bob).
  2. `Alice–Eve1-Alice`: Correlation between Alice's transmission and Eve's eavesdropping (u = Alice, v = Eve1-Alice).
  3. `Bob–Eve1-Bob`: Correlation between Bob's transmission and Eve's eavesdropping (u = Bob, v = Eve1-Bob).

### Pre- vs. Post-Filtering Correlation Results ($N=500$, `data_kind=dummy`)

| Channel Pair | Raw Correlation ($\rho_{\text{raw}}$) | Filtered Correlation ($\rho_{\text{filt}}$) | Change ($\Delta\rho$) |
| :--- | :--- | :--- | :--- |
| `Alice–Bob` | `+0.632263` | `+0.842244` | `+0.209981` |
| `Alice–Eve1-Alice` | `+0.017060` | `-0.013725` | `-0.030784` |
| `Bob–Eve1-Bob` | `+0.119310` | `+0.015151` | `-0.104159` |

*(Note: MSHKF filtering enhances legitimate reciprocal correlation for Alice–Bob while suppressing eavesdropper Eve's channel correlation toward zero on the software-validation dummy dataset).*

---

## Quantization Stage Implementation (Modified Adaptive Dual-Threshold Quantization)

- **Methodological Reference**: Governed by `PA.pdf`, **Section 3.2.3, Equations (3.21)–(3.23), pages 27–28**, with performance evaluation via Key Agreement Rate (KAR) in **Section 3.2.8.c, Equation (3.64), page 35**:
  - **Non-overlapping Adaptive Segmentation**:
    The filtered RSSI sample sequence is partitioned into non-overlapping segments of length $W$ (configurable, default $W = 50$). For each segment $s$ and each channel independently, the local mean $\mu_X$ and population standard deviation $\sigma_X$ ($\text{ddof} = 0$) are computed:

    $$
    \mu_X = \frac{1}{M}\sum_{i=1}^{M} X_i, \qquad \sigma_X = \sqrt{\frac{1}{M}\sum_{i=1}^{M} (X_i - \mu_X)^2}
    $$

  - **Adaptive Threshold Calculation**:
    The upper threshold $q_i^+$ and lower threshold $q_i^-$ are determined per segment:

    $$
    q_i^+ = \mu_X + \alpha \sigma_X \qquad (3.21)
    $$

    $$
    q_i^- = \mu_X - \alpha \sigma_X \qquad (3.22)
    $$

    where $\alpha$ is a sensitivity multiplier (default $\alpha = 0.5$).

  - **Quantization Level Assignment**:
    Each sample $X_i$ is mapped into a discrete quantization level:

    $$
    Q(X_i) = \begin{cases}
    0, & X_i < q_i^- \\
    1, & q_i^- \le X_i \le q_i^+ \\
    2, & X_i > q_i^+
    \end{cases} \qquad (3.23)
    $$

  - **Sample Retention Policy**:
    Unlike conventional discard-based quantization schemes, Modified ADQ retains every sample. Samples falling in the intermediate zone $[q_i^-, q_i^+]$ are assigned to level 1 and retained for bit encoding. Constant segments ($\sigma_X = 0$) unconditionally produce level 1. Partial final segments (length $< W$) are fully processed with their own local mean and standard deviation.

  - **Dual Binary Encodings (Generated Simultaneously)**:
    - **2-bit Gray Code** (implementation choice):
      $$0 \rightarrow 00, \quad 1 \rightarrow 01, \quad 2 \rightarrow 11$$
      Minimizes bit errors for small-scale signal fluctuations because adjacent quantization levels differ by exactly one bit.
    - **4-bit Representation** (per `PA.pdf` Section 3.2.3, page 28):
      $$0 \rightarrow 1010, \quad 1 \rightarrow 1011, \quad 2 \rightarrow 1001$$
      Each quantization level is expanded into a 4-bit binary codeword.

### Quantization Configuration Parameters & Rationale

| Parameter | Default Value | Specification Status | Rationale |
| :--- | :--- | :--- | :--- |
| `window_size` ($W$) | `50` | Provisional Software-Validation Setting | Non-overlapping segment size. Selected as a provisional setting for pipeline validation, not an optimized physical-channel parameter. |
| `alpha` ($\alpha$) | `0.5` | Provisional Software-Validation Setting | Sensitivity multiplier controlling threshold spread around segment mean. Selected as a provisional setting for pipeline validation, not an optimized physical-channel parameter. |
| `ddof` | `0` | Specification Assumption | Population standard deviation used for exact segment dispersion. |
| Encodings | Both in same run | Explicit (`PA.pdf` Section 3.2.3) | Both 2-bit Gray and 4-bit bitstreams are extracted simultaneously per channel to enable direct comparison. |

### Evaluation Metrics: Key Agreement Rate (KAR) & Level Agreement

Key Agreement Rate is computed at the bit level per `PA.pdf` Equation (3.64):

$$
\text{KAR} = \left(1 - \frac{N_{\text{mismatch}}}{N_{\text{total}}}\right) \times 100\% = \frac{N_{\text{total}} - N_{\text{mismatch}}}{N_{\text{total}}} \times 100\% \qquad (3.64)
$$

where $N_{\text{total}}$ is total compared bits and $N_{\text{mismatch}}$ is number of differing bit positions.

In addition, the **Sample-Level Agreement Rate** is computed as the proportion of samples where discrete levels match ($Q(X_{A,i}) = Q(X_{B,i})$):

$$
\text{Agreement}_{\text{level}} = \frac{1}{N}\sum_{i=1}^{N} \mathbf{1}\left(Q(X_{A,i}) = Q(X_{B,i})\right) \times 100\%
$$

### Measured Quantization Results ($N=500$, $W=50$, $\alpha=0.5$, `data_kind=dummy`)

| Pair | Samples | Level Agreement | 2-bit Gray KAR | 4-bit KAR | Bit Count (2b / 4b) |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `Alice–Bob` | 500 | `64.4000%` | `80.4000%` | `90.2000%` | 1,000 / 2,000 |
| `Alice–Eve1-Alice` | 500 | `34.8000%` | `58.2000%` | `79.1000%` | 1,000 / 2,000 |
| `Bob–Eve1-Bob` | 500 | `34.4000%` | `55.4000%` | `77.7000%` | 1,000 / 2,000 |

#### Quantization Level Distributions per Channel

| Channel | Total Samples | Level 0 ($X_i < q_i^-$) | Level 1 ($q_i^- \le X_i \le q_i^+$) | Level 2 ($X_i > q_i^+$) |
| :--- | :--- | :--- | :--- | :--- |
| `Alice` | 500 | 127 (25.40%) | 219 (43.80%) | 154 (30.80%) |
| `Bob` | 500 | 169 (33.80%) | 161 (32.20%) | 170 (34.00%) |
| `Eve1-Alice` | 500 | 147 (29.40%) | 193 (38.60%) | 160 (32.00%) |
| `Eve1-Bob` | 500 | 164 (32.80%) | 147 (29.40%) | 189 (37.80%) |

> [!IMPORTANT]
> **Critical Encoding Insight & Entropy Warning**:
> In the 4-bit code (`1010`, `1011`, `1001`), the prefix bits `10` are identical across all three codewords. As a result, at least 50% of bits match unconditionally regardless of quantization level, elevating eavesdropper KAR to ~77–79% even when sample-level agreement is only ~34%. Reporting level agreement alongside bit-level KAR is essential to maintain transparency so that encoding artifacts remain visible. **Encoded bit length must never be equated with physical entropy or cryptographic security.**

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
The test suite comprises 50 automated tests (MSHKF step-by-step intermediate numerical equations, channel isolation, sample indexing, numerical safeguards, Pearson correlation, workbook loading, visualization generation, MADQ threshold calculations, exact boundary conditions, encodings, KAR validation, companion XLSX string-cell formatting with leading zero preservation and >32k character limit chunking, and KAR comparison plotting):

```powershell
# Run all unit tests (50 tests)
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

#### C. Full Execution with MSHKF Filtering & Modified ADQ Quantization Stages
Run the CLI with both `--filter` and `--quantize` (or `--quantize` alone, which automatically invokes filtering as a prerequisite) along with full artifact export, companion XLSX workbook, and KAR comparison charts:
```powershell
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --quantize `
  --quantize-window 50 `
  --quantize-alpha 0.5 `
  --filtered-samples-output "outputs/dummy_rssi_filtered_samples.csv" `
  --filter-config-output "outputs/dummy_rssi_filter_config.json" `
  --quantized-samples-output "outputs/dummy_rssi_quantized_samples.csv" `
  --quantized-segments-output "outputs/dummy_rssi_quantized_segments.csv" `
  --quantized-bitstreams-output "outputs/dummy_rssi_quantized_bitstreams.csv" `
  --quantize-metrics-output "outputs/dummy_rssi_quantize_metrics.csv" `
  --quantize-config-output "outputs/dummy_rssi_quantize_config.json" `
  --quantized-xlsx-output "outputs/dummy_rssi_quantized.xlsx" `
  --figure-prefix "outputs/dummy_rssi_filtered"
```

> [!TIP]
> **Microsoft Excel Guidance for Leading Zeros (`00` vs `0`, `01` vs `1`)**:
> - The raw CSV export (`outputs/dummy_rssi_quantized_samples.csv`) preserves exact string literals (`"00"`, `"01"`). However, Microsoft Excel automatically strips leading zeros when directly double-clicking a CSV file, displaying `00` as `0` and `01` as `1`.
> - **Excel users should open the companion XLSX workbook** (`outputs/dummy_rssi_quantized.xlsx`) instead of the CSV. In the XLSX export, all bitstream strings and sample codes are stored explicitly as string cells (`data_type='s'`) with Text format (`@`), ensuring leading zeros are preserved identically across all spreadsheet viewers.
> - For bitstreams exceeding Excel's single-cell limit of 32,767 characters, the XLSX exporter automatically chunks long bit sequences across sequential rows (`part`, `total_parts`) so that data is never silently truncated.

### 4. Output File Locations (`outputs/`)
All generated artifacts are stored in the `outputs/` directory (ignored by Git via `.gitignore`, except `.gitkeep`):
- `outputs/dummy_rssi_correlation.csv`: Raw correlation coefficients table for all three channel pairs (N = 500).
- `outputs/dummy_rssi_correlation.png` / `.pdf`: Raw correlation visualization charts (horizontal bar + bubble scatter).
- `outputs/dummy_rssi_filtered_correlation.csv`: Comparative table of raw vs. filtered correlation coefficients along with Δρ.
- `outputs/dummy_rssi_filtered_samples.csv`: Time-aligned row-by-row raw and filtered observation samples across all 4 channels.
- `outputs/dummy_rssi_filter_config.json`: Complete MSHKF configuration metadata, modeling assumptions, units, and rationale.
- `outputs/dummy_rssi_quantized_samples.csv`: Time-aligned row-by-row filtered RSSI, segment index, thresholds, levels, and dual bit encodings per sample (clean machine-readable CSV).
- `outputs/dummy_rssi_quantized_segments.csv`: Per-segment local statistics (mean, population std) and lower/upper thresholds per channel.
- `outputs/dummy_rssi_quantized_bitstreams.csv`: Continuous binary bitstreams for both 2-bit Gray and 4-bit representations per channel.
- `outputs/dummy_rssi_quantize_metrics.csv`: Key Agreement Rate (KAR), Level Agreement Rate, and bit count metrics for evaluated channel pairs.
- `outputs/dummy_rssi_quantize_config.json`: Complete quantization configuration metadata, rationale, and execution summary.
- `outputs/dummy_rssi_quantized.xlsx`: Companion multi-sheet Excel workbook (`Quantized Samples`, `Bitstreams`, `Agreement Metrics`, `Segment Thresholds`) with explicit Text formatting preserving leading zeros and handling the 32,767 cell character limit.
- `outputs/dummy_rssi_filtered.png` & `.pdf`: High-resolution (300 dpi) and vector PDF comparative MSHKF filtering visualizations.
- `outputs/dummy_rssi_quantization.png` & `.pdf`: High-resolution (300 dpi) and vector PDF KAR comparison figure (grouped 2-bit vs. 4-bit KAR bars, sample-level agreement panel, metrics summary table, and mathematical explanation of the fixed-prefix effect $\text{KAR}_{\text{4bit}} = 50\% + \text{KAR}_{\text{2bit}} / 2$).

---

## Methodological Limitations & Warnings

The results of this analysis are strictly for **software validation** using synthetic dummy data. The resulting correlation coefficients and Key Agreement Rates **must not be used to draw empirical security conclusions or characterize real physical channel propagation**, as physical channel probing is postponed, not replaced. Parameters such as $W=50$ and $\alpha=0.5$ are provisional software-validation settings, not optimized physical-channel parameters.
