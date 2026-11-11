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
│   └── rssi_skg/                     # Main Python source package modules (loader, filter, correlation, plotting, quantization, prbs, reconciliation, privacy_amplification, nist, kgr, cli)
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── correlation.py
│       ├── filter.py
│       ├── kgr.py
│       ├── loader.py
│       ├── nist.py
│       ├── plotting.py
│       ├── prbs.py
│       ├── privacy_amplification.py
│       ├── quantization.py
│       └── reconciliation.py
├── tests/                            # Unit tests and software validation
│   ├── __init__.py
│   ├── test_correlation.py
│   ├── test_filter.py
│   ├── test_kgr.py
│   ├── test_loader.py
│   ├── test_nist.py
│   ├── test_plotting.py
│   ├── test_prbs.py
│   ├── test_privacy_amplification.py
│   ├── test_quantization.py
│   └── test_reconciliation.py
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
  - `prbs.py`: Galois XOR-LFSR bit expansion engine, per-sample seed initialization, zero-seed lockup handling, and multi-channel KAR evaluation (`PA.pdf` Section 3.2.4 as background).
  - `reconciliation.py`: Codeword-based helper data BCH information reconciliation, zero-padding lifecycle, multi-pair evaluator, and companion XLSX exporter (`PA.pdf` Section 3.2.5).
  - `privacy_amplification.py`: Bit-level SHA-256 Privacy Amplification engine, FIPS PUB 180-4 padding, 256-bit secret key extraction, and multi-channel KAR evaluation (`PA.pdf` Section 3.2.6, Equations 3.37–3.53).
  - `nist.py`: NIST SP 800-22 Rev. 1a statistical test suite (Frequency Monobit, Runs, Approximate Entropy) and acceptance gating (`PA.pdf` Section 3.2.8.d, Equations 3.65–3.73).
  - `kgr.py`: Key Generation Rate (KGR) measurement, high-resolution monotonic timer, BCH cache warm-up, and multi-sheet evaluation Excel workbook (`PA.pdf` Section 3.2.8.b, Equation 3.63).
  - `plotting.py`: Aggregate bubble scatter visualization, pre-/post-filtering comparison plots, KAR comparison charts, 4-panel reconciliation analysis figures, and 2×2 privacy amplification KAR comparison figures.
  - `cli.py`: Unified CLI supporting pure correlation mode (default), optional filtering, quantization, PRBS expansion, BCH reconciliation, Privacy Amplification, NIST statistical randomness testing, and Key Generation Rate (KGR) measurement.
- `tests/`: Automated unit tests ensuring algorithmic correctness, channel isolation, numerical safeguards, exact boundary conditions, encodings, PRBS maximal periods, BCH error correction, receiver isolation, canonical hashing, NIST reference vector validation, mock clock KGR measurement, eavesdropper threat model regression, and full pipeline testing (119 tests).
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
    - State transition matrix $`\Phi = 1.0`$ (static/slowly varying channel RSSI model: $`X_k = X_{k-1} + q_{k-1} + w_{k-1}`$).
    - Measurement matrix $`H = 1.0`$ (direct scalar RSSI observation in dBm: $`Z_k = X_k + r_k + v_k`$).
  - **Noise Adaptation Mode**:
    - The fixed scalar process-noise covariance Q is held constant at 0.1 (dBm)².
    - The adaptive measurement-noise covariance $`\hat{R}_k`$ is estimated online via Equation (3.15).
    - The noise means q and r ($`\hat{q}_k`$ and $`\hat{r}_k`$) are recursively updated via Equations (3.19) and (3.13).
  - **Rationale for Omitting Adaptive $Q$ Update (Equation 3.20)**:
    This implementation specifically follows the modeling assumption stated in the final paragraph of `PA.pdf` Section 3.2.2 (page 27), where the process-noise covariance $Q$ is assumed to be known and held fixed (*known prior*). Consequently, the measurement-noise covariance $`\hat{R}_k`$ is adaptively estimated online and the adaptive $Q$ update in Equation (3.20) is not executed.

### Preserved Calculation Sequence (Equations 3.10–3.19)

**a. Adaptive weight (Equation 3.10)**

```math
D_k = \frac{D_{k-1}}{D_{k-1} + b}, \qquad D_0 = 1
```

**b. State prediction (Equation 3.11)**

```math
\hat{X}(k|k-1) = \Phi \hat{X}_{k-1} + \hat{q}_{k-1}
```

**c. Error covariance prediction (Equation 3.12)**

```math
P(k|k-1) = \Phi P_{k-1} \Phi^T + Q
```

**d. Measurement noise mean update (Equation 3.13)**

```math
\hat{r}_k = (1 - D_k)\hat{r}_{k-1} + D_k \left(Z_k - H \hat{X}(k|k-1)\right)
```

**e. Innovation calculation using updated $`\hat{r}_k`$ (Equation 3.14)**

```math
e_k = Z_k - H \hat{X}(k|k-1) - \hat{r}_k
```

**f. Measurement noise covariance update (Equation 3.15)**

```math
\hat{R}_k = (1 - D_k)\hat{R}_{k-1} + D_k e_k^2
```

**g. Kalman gain (Equation 3.16)**

```math
K_k = \frac{P(k|k-1) H^T}{H P(k|k-1) H^T + \hat{R}_k}
```

**h. State update (Equation 3.17)**

```math
\hat{X}_k = \hat{X}(k|k-1) + K_k e_k
```

**i. Error covariance update (Equation 3.18)**

```math
P_k = (1 - K_k H) P(k|k-1)
```

**j. Process noise mean update (Equation 3.19)**

```math
\hat{q}_k = (1 - D_k)\hat{q}_{k-1} + D_k \left(\hat{X}_k - \Phi \hat{X}_{k-1}\right)
```

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
- When $x_0$ is automatically initialized from the first observation ($x_0 = z_0$), the sample $z_0$ is assigned directly as the state at time index 0 ($`\hat{X}_0 = z_0`$). The recursive update loop of Equations (3.10)–(3.19) starts from measurement $z_1$ at step $k=1$. Thus, $z_0$ is used exactly once as the initial condition and **is never re-fed as a measurement innovation input**.
- If a prior $x_0$ is explicitly supplied externally, all measurements $`z_0, \dots, z_{N-1}`$ are processed through steps $`k = 1, \dots, N`$.

### Channel Isolation & Numerical Safeguards
- **Channel Isolation**: The Alice, Bob, Eve1-Alice, and Eve1-Bob channels are filtered using separate, independent filter instances. No state is shared across channels.
- **Finite-Value Validation**: Enforces `math.isfinite` across all input samples; explicitly rejects `NaN`, `+Inf`, and `-Inf`.
- **Covariance Safeguards**: Enforces non-negative error covariance ($`P_k \ge 0.0`$), validates that the Kalman gain denominator is strictly non-singular ($`P(k|k-1) + \hat{R}_k > 0`$), and raises `FloatingPointError` if significant negative covariance or non-finite values occur (never silently masked).

The measurement-noise covariance lower-bound constraint is enforced at each step:

```math
\hat{R}_k \ge R_{\min} = 10^{-8}\,(\mathrm{dBm})^2
```

---

## Correlation Stage Implementation (Pearson Correlation)

- **Methodological Reference**: Governed by `PA.pdf`, **Equation (3.62), page 34**:

```math
\rho_{u,v} =
\frac{
\sum_{n=1}^{N}
\left(X_u(n)-\mu_u\right)
\left(X_v(n)-\mu_v\right)
}{
\sqrt{\sum_{n=1}^{N}\left(X_u(n)-\mu_u\right)^2}
\sqrt{\sum_{n=1}^{N}\left(X_v(n)-\mu_v\right)^2}
}
```

Where:
- $`X_u(n)`$: RSSI sample value on channel $u$ at observation index $n$.
- $`X_v(n)`$: RSSI sample value on channel $v$ at observation index $n$.
- $`\mu_u`$: Sample mean of channel $u$ RSSI over $N$ observations.
- $`\mu_v`$: Sample mean of channel $v$ RSSI over $N$ observations.
- $N$: Total number of paired observations (N = 500 in the dummy validation dataset).

Sample mean of channel $u$:

```math
\mu_u = \frac{1}{N}\sum_{n=1}^{N} X_u(n)
```

Sample mean of channel $v$:

```math
\mu_v = \frac{1}{N}\sum_{n=1}^{N} X_v(n)
```

*(Note: The channel labels u and v correspond to the earlier X and Y notation).*
- **Analysis Nature**: Pearson correlation is computed at zero lag.
- **Evaluated Channel Pairs (Observation Comparisons)**:
  1. `Alice–Bob`: Reciprocity estimate between legitimate communication partners (u = Alice, v = Bob).
  2. `Alice–Eve1-Alice`: Observation comparison between Alice's transmission received by Bob/Alice and Eve's passive observation (u = Alice, v = Eve1-Alice).
  3. `Bob–Eve1-Bob`: Observation comparison between Bob's transmission and Eve's passive observation (u = Bob, v = Eve1-Bob).
  *(Note: Pre-reconciliation pairs represent physical receiver observation comparisons, NOT communication sessions. Eve never participates as a legitimate communication peer).*

### Pre- vs. Post-Filtering Correlation Results ($N=500$, `data_kind=dummy`)

| Channel Pair | Raw Correlation ($`\rho_{\text{raw}}`$) | Filtered Correlation ($`\rho_{\text{filt}}`$) | Change ($`\Delta\rho`$) |
| :--- | :--- | :--- | :--- |
| `Alice–Bob` | `+0.632263` | `+0.842244` | `+0.209981` |
| `Alice–Eve1-Alice` | `+0.017060` | `-0.013725` | `-0.030784` |
| `Bob–Eve1-Bob` | `+0.119310` | `+0.015151` | `-0.104159` |

*(Note: MSHKF filtering enhances legitimate reciprocal correlation for Alice–Bob while suppressing eavesdropper Eve's channel correlation toward zero on the software-validation dummy dataset).*

---

## Quantization Stage Implementation (Modified Adaptive Dual-Threshold Quantization)

- **Methodological Reference**: Governed by `PA.pdf`, **Section 3.2.3, Equations (3.21)–(3.23), pages 27–28**, with performance evaluation via Key Agreement Rate (KAR) in **Section 3.2.8.c, Equation (3.64), page 35**:

- **Non-overlapping Adaptive Segmentation**:
  The filtered RSSI sample sequence is partitioned into non-overlapping segments of length $W$ (configurable, default $W = 50$). For each segment $s$ and each channel independently, the local mean $`\mu_X`$ and population standard deviation $`\sigma_X`$ ($`\text{ddof} = 0`$) are computed:

```math
\mu_X = \frac{1}{M}\sum_{i=1}^{M} X_i,
\qquad
\sigma_X = \sqrt{\frac{1}{M}\sum_{i=1}^{M}(X_i-\mu_X)^2}
```

- **Adaptive Threshold Calculation**:
  The upper threshold $`q_i^+`$ and lower threshold $`q_i^-`$ are determined per segment:

```math
q_i^+ = \mu_X + \alpha\sigma_X \qquad (3.21)
```

```math
q_i^- = \mu_X - \alpha\sigma_X \qquad (3.22)
```

  where $\alpha$ is a sensitivity multiplier (default $\alpha = 0.5$).

- **Quantization Level Assignment**:
  Each sample $X_i$ is mapped into a discrete quantization level:

```math
Q(X_i)=
\begin{cases}
0, & X_i < q_i^- \\
1, & q_i^- \le X_i \le q_i^+ \\
2, & X_i > q_i^+
\end{cases}
\qquad (3.23)
```

- **Sample Retention Policy**:
  Unlike conventional discard-based quantization schemes, Modified ADQ retains every sample. Samples falling in the intermediate zone $`[q_i^-, q_i^+]`$ are assigned to level 1 and retained for bit encoding. Constant segments ($`\sigma_X = 0`$) unconditionally produce level 1. Partial final segments (length $< W$) are fully processed with their own local mean and standard deviation.

- **Dual Binary Encodings (Generated Simultaneously)**:
  Each discrete quantization level is mapped into both a 2-bit Gray code and a 4-bit representation simultaneously:

| Level | 2-bit Gray code | 4-bit representation |
| :---: | :---: | :---: |
| 0 | `00` | `1010` |
| 1 | `01` | `1011` |
| 2 | `11` | `1001` |

  - **2-bit Gray Code** (implementation choice): Minimizes bit errors for small-scale signal fluctuations because adjacent quantization levels differ by exactly one bit.
  - **4-bit Representation** (per `PA.pdf` Section 3.2.3, page 28): Each quantization level is expanded into a 4-bit binary codeword.

### Quantization Configuration Parameters & Rationale

| Parameter | Default Value | Specification Status | Rationale |
| :--- | :--- | :--- | :--- |
| `window_size` ($W$) | `50` | Provisional Software-Validation Setting | Non-overlapping segment size. Selected as a provisional setting for pipeline validation, not an optimized physical-channel parameter. |
| `alpha` ($\alpha$) | `0.5` | Provisional Software-Validation Setting | Sensitivity multiplier controlling threshold spread around segment mean. Selected as a provisional setting for pipeline validation, not an optimized physical-channel parameter. |
| `ddof` | `0` | Specification Assumption | Population standard deviation used for exact segment dispersion. |
| Encodings | Both in same run | Explicit (`PA.pdf` Section 3.2.3) | Both 2-bit Gray and 4-bit bitstreams are extracted simultaneously per channel to enable direct comparison. |

### Evaluation Metrics: Key Agreement Rate (KAR) & Level Agreement

Key Agreement Rate is computed at the bit level per `PA.pdf` Equation (3.64):

```math
\text{KAR} = \left(1 - \frac{N_{\text{mismatch}}}{N_{\text{total}}}\right) \times 100\% = \frac{N_{\text{total}} - N_{\text{mismatch}}}{N_{\text{total}}} \times 100\% \qquad (3.64)
```

where $`N_{\text{total}}`$ is total compared bits and $`N_{\text{mismatch}}`$ is number of differing bit positions.

In addition, the **Sample-Level Agreement Rate** is computed as the proportion of samples where discrete levels match ($`Q(X_{A,i}) = Q(X_{B,i})`$):

```math
\text{Agreement}_{\text{level}} = \frac{1}{N}\sum_{i=1}^{N} \mathbf{1}\left(Q(X_{A,i}) = Q(X_{B,i})\right) \times 100\%
```

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

## PRBS Expansion Stage Implementation (Galois XOR-LFSR)

- **Methodological Reference**: Governed by `PA.pdf`, **Section 3.2.4 (pages 28–29)** as background (with characteristic polynomial Equation 3.24 and maximal-period length Equation 3.26), with performance evaluation via Key Agreement Rate (KAR) in **Section 3.2.8.c, Equation (3.64), page 35**.

### Mathematical Recurrence & Galois Configuration
A Pseudo-Random Binary Sequence (PRBS) is generated using an $m$-stage Linear Feedback Shift Register (LFSR) defined by a characteristic polynomial:

```math
f(x) = c_m x^m + c_{m-1} x^{m-1} + \dots + c_1 x + c_0 \qquad (3.24)
```

where $`c_i \in \{0, 1\}`$, $`c_m = 1`$, and $`c_0 = 1`$.

`PA.pdf` Equation (3.25) defines the **scalar output recurrence relation**:

```math
S_{i+m} = \left(\sum_{j=0}^{m-1} C_j S_{i+j}\right) \bmod 2 \qquad (3.25)
```

- **Output Recurrence vs. Galois State Update**:
  - **Equation 3.25** describes the scalar recurrence governing the emitted output bitstream ($S_{i+2} = S_i \oplus S_{i+1}$ for $m=2$, and $S_{i+4} = S_i \oplus S_{i+1}$ for $m=4$). This recurrence is mathematically satisfied by output bit sequences generated by Galois LFSRs as well as Fibonacci LFSRs.
  - While classical Fibonacci LFSRs store past output bits directly in a delay chain, the **Galois LFSR** implemented here updates the internal vector register state in-place at each clock cycle using bitwise shifts and internal conditional XOR feedback taps:

```math
S_{k+1} = \left((S_k \ll 1) \wedge (2^m - 1)\right) \oplus \left(c \cdot \text{MSB}(S_k)\right)
```

- **Bitwise Operators in Recurrence**:
  - $`\ll 1`$: Bitwise left-shift by 1 bit.
  - $`\wedge`$: Bitwise AND with mask $`(2^m - 1)`$ to constrain state within register degree $`m`$.
  - $`\oplus`$: Bitwise XOR (modulo-2 addition).
  - $`\text{MSB}(S_k)`$: Most significant bit emitted at step $`k`$ (`(state >> (m - 1)) & 1`), which gates the feedback polynomial mask $`c`$.
- **Register Seeds vs. Initial Output Bits**: The quantization codeword initializes the internal Galois register state vector. Due to internal XOR feedback taps during left shifts, the first $m$ emitted bits are a linear isomorphism of the initial seed, not necessarily identical bit-by-bit to the seed string for all states (e.g. $m=2$ seed `'10'` emits `'11'`, seed `'11'` emits `'10'`, and $m=4$ codeword `'1010'` emits `'1011'`). Regardless, the resulting output sequence strictly satisfies Equation (3.25) at all steps $i \ge 0$.
- **Per-Sample Deterministic Resets & Boundary Behavior**: Each sample's quantization encoding is fed as an exact seed into the LFSR. The LFSR state is reset to that sample's seed, stepped exactly $`2^m - 1`$ times to emit $`2^m - 1`$ bits, and the expanded bits are concatenated in the original temporal sample sequence. The two encoding paths are processed completely independently across Alice, Bob, Eve1-Alice, and Eve1-Bob. **Recurrence under Equation (3.25) holds strictly within each uninterrupted sample block; it is not guaranteed across concatenated sample boundaries (some transitions may satisfy it coincidentally, but it does not hold in general)** because the register is re-initialized deterministically at each new sample.

### Primitive Polynomials & Register Sizes
The register degree $m$ and per-sample resets are explicit implementation choices matching quantization codeword lengths:
1. **2-bit Path ($m=2$)**:
   - Primitive polynomial: $`f(x) = x^2 + x + 1`$
   - Galois feedback mask: `0b11` (integer 3)
   - Requested output length: exactly **8 bits per sample** (8 LFSR clocks executed per sample; 4,000 bits per channel for 500 samples).
   - Maximal period: $`L = 2^2 - 1 = 3`$ for any non-zero seed (`01`, `11`).
2. **4-bit Path ($m=4$)**:
   - Primitive polynomial: $`f(x) = x^4 + x + 1`$
   - Galois feedback mask: `0b0011` (integer 3)
   - Requested output length: exactly **8 bits per sample** (8 LFSR clocks executed per sample; 4,000 bits per channel for 500 samples).
   - Maximal period: $`L = 2^4 - 1 = 15`$ for any non-zero seed (`1010`, `1011`, `1001`).

> [!NOTE]
> **Distinction Between Degree, Maximal Period, and Output Length**:
> For both paths, exactly 8 clocks are executed per sample, yielding 8 output bits per sample. The register degree remains $m=2$ and $m=4$, respectively (not changed to degree 8), and maximal periods remain $2^2-1=3$ and $2^4-1=15$. Eight output bits does NOT imply eight independent entropy bits.

### Zero-Seed Handling (Deliberate Exception to `PA.pdf`)
In `PA.pdf` Section 3.2.4, an LFSR is assumed to operate from a non-zero initial seed because the all-zero state produces no feedback (`0 ^ 0 = 0`). In this research pipeline:
- **Zero-seed `"00"` is strictly preserved** and is **NEVER** remapped to `"10"` or any other state.
- Samples are **never discarded**, reseeded, or injected with artificial randomness.
- Standard Galois XOR recurrence runs unmodified: state 0 locks up at state 0, producing exactly `"00000000"` (8 zeros).
- Each sample records `is_zero_state = True` and `actual_period = 1`.
- The requested output length (8 bits) is rigorously distinguished from the actual period (1). Maximal-period guarantees apply strictly to non-zero seeds with primitive polynomials.

### Pre- vs. Post-PRBS Key Agreement Rate (KAR) ($N=500$, `data_kind=dummy`, 8 bits/sample)

| Channel Pair | Pre-PRBS 2-bit KAR | Post-PRBS 2-bit KAR | Δ 2-bit KAR | Pre-PRBS 4-bit KAR | Post-PRBS 4-bit KAR | Δ 4-bit KAR |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| `Alice–Bob` | `80.4000%` | `75.8500%` (3034/4000) | `-4.5500 pp` | `90.2000%` | `86.2000%` (3448/4000) | `-4.0000 pp` |
| `Alice–Eve1-Alice` | `58.2000%` | `56.1000%` (2244/4000) | `-2.1000 pp` | `79.1000%` | `73.2500%` (2930/4000) | `-5.8500 pp` |
| `Bob–Eve1-Bob` | `55.4000%` | `56.3750%` (2255/4000) | `+0.9750 pp` | `77.7000%` | `72.4500%` (2898/4000) | `-5.2500 pp` |

#### Zero-Seed Distribution per Channel ($N=500$ samples)
- **2-bit Gray Path**:
  - `Alice`: 127 zero seeds (25.40%)
  - `Bob`: 169 zero seeds (33.80%)
  - `Eve1-Alice`: 147 zero seeds (29.40%)
  - `Eve1-Bob`: 164 zero seeds (32.80%)
- **4-bit Path**:
  - `Alice`: 0 zero seeds (0.00%)
  - `Bob`: 0 zero seeds (0.00%)
  - `Eve1-Alice`: 0 zero seeds (0.00%)
  - `Eve1-Bob`: 0 zero seeds (0.00%)

> [!WARNING]
> **Scientific Limitation & Information-Theoretic Entropy Warning**:
> Deterministic Galois LFSR expansion **does not add physical channel entropy or cryptographic security**. A pseudo-random sequence is entirely determined by its seed. Repeated quantization levels produce identical expanded output blocks.
> Furthermore, KAR can and does decrease after expansion: In the 4-bit quantization scheme, all codewords share the static `'10'` prefix (forcing a 50% minimum match). The LFSR expands and disperses these bits across 15 pseudo-random cycle states, diffusing the prefix artifact and pulling the observed KAR closer to the true underlying sample-level agreement rate (~64.4% for Alice–Bob and ~34% for Eve).

---

## BCH Information Reconciliation Stage (PA.pdf Section 3.2.5)

Governed by `PA.pdf` **Section 3.2.5, Equations (3.27)–(3.36), pages 29–33**:

> [!NOTE]
> **Scope Clarification**: This stage performs **BCH Information Reconciliation only** per `PA.pdf` Section 3.2.5. Privacy Amplification (`PA.pdf` Section 3.2.6) is a separate future stage requiring a separate request and is NOT part of this implementation.

### 1. Codeword-Based Helper Data Mechanism (Equations 3.32–3.36)
Unlike syndrome-only reconciliation, codeword-based reconciliation operates by embedding an independent random codeword into public helper data:
1. **Source $A$ (Alice)** partitions unpadded source stream $A$ into blocks of length $n$ (zero-padding final block if length is not a multiple of $n$).
2. For each block, Alice generates an independent random message $u \in \{0, 1\}^k$ and encodes it into a valid BCH codeword $C = \text{BCH.encode}(u)$ of length $n$.
3. Alice calculates and publishes helper data $H = A \oplus C$ (`PA.pdf` Eq 3.32).
4. **Receiver $B$ (Bob)** computes $C' = H \oplus B = (A \oplus C) \oplus B = C \oplus (A \oplus B)$ (`PA.pdf` Eq 3.33). Because $A \oplus B$ represents channel bit errors, $C'$ is codeword $C$ corrupted by channel errors.
5. Bob decodes $C'$ using the BCH decoder (`galois.BCH.decode`) to obtain candidate codeword $\hat{C}$ and corrected error count $e$.
6. Bob reconstructs Alice's bitstream via $\hat{A} = H \oplus \hat{C}$ (`PA.pdf` Eq 3.36).
7. Receiver decoding strictly accesses only Bob's own bits $B$, public helper data $H$, and public code parameters $(n, k, t)$. No source bits or random messages $u$ are ever exposed to the receiver.
8. Zero-padding bits are stripped post-reconstruction; original lengths are strictly restored, and padding is excluded from payload metrics and hashing.

### 2. BCH Code Parameter Selection & Four-Path Results ($N=500$, `data_kind=dummy`)

#### Baseline Error Verification ($n=127$, Sequential Layout)
Recomputing per-block errors on the revised $N=500$ dummy dataset under sequential splitting with zero-padding reveals:
- **`quant_4bit`** ($L=2000$ bits, 16 blocks of length 127, 32 pad bits):
  - Alice–Bob errors per block: $\min = 3$, $\text{avg} = 12.25$, $\max = \mathbf{23}$ (18.1% max block BER).
- **`prbs_4bit`** ($L=4000$ bits, 32 blocks of length 127, 64 pad bits):
  - Alice–Bob errors per block: $\min = 0$, $\text{avg} = 17.25$, $\max = \mathbf{36}$ (28.3% max block BER).
- *Obsolete Recommendation Removal*: Under this block layout, previous hypothetical suggestions of $t=14$ (for `quant_4bit`) and $t=21$ (for `prbs_4bit`) cannot correct the observed maximum errors ($23 > 14$ and $36 > 21$) and fail exact Bob reconstruction. They have been removed as unsupported.

#### Candidate Search & Comparison for Shared 4-Bit BCH ($k > 1$)
A bounded, cached candidate search over valid narrow-sense primitive binary BCH codes in Galois ($n \in \{31, 63, 127, 255, 511, 1023\}$) was executed, requiring $t$ to cover every observed Alice–Bob block error across both 4-bit paths while excluding $k=1$ from recommended configurations:
- For $n \le 127$: The maximum error on `prbs_4bit` at $n=127$ is 36. Any binary BCH code with $n=127$ and $t \ge 32$ forces $k=1$. No code with $k > 1$ exists for $n \le 127$ that corrects 36 errors.
- For $n=255$: Block error counts are $\max = 42$ (16.5%) on `quant_4bit` and $\max = 62$ (24.3%) on `prbs_4bit`. The minimal candidate satisfying $t \ge 62$ with $k > 1$ is **$\text{BCH}(255, 9, 63)$** with designed distance $d = 127$.
- For $n=511$: Block error counts are $\max = 81$ on `quant_4bit` and $\max = 116$ on `prbs_4bit`. The code is $\text{BCH}(511, 19, 116, d=233)$.
- For $n=1023$: Block error counts are $\max = 111$ on `quant_4bit` and $\max = 222$ on `prbs_4bit`. The code is $\text{BCH}(1023, 36, 222, d=445)$.

| Candidate | Code ($n, k, t, d$) | Code Rate ($k/n$) | `quant_4bit` (Blks/Pad) | `prbs_4bit` (Blks/Pad) | Public Helper (4b/PRBS) | Bob Exact Recovery | Eve Recovery (`q_4b` / `p_4b`) | Selection Status |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **Baseline ($k=1$)** | $\text{BCH}(127, 1, 62, 125)$ | 0.00787 | 16 blks / 32b | 32 blks / 64b | 2032b / 4064b | TRUE / TRUE | **100% / 100% (EXACT)** | Baseline only ($k=1$, 99.2% leakage) |
| **Candidate A** | **$\text{BCH}(255, 9, 63, 127)$** | **0.03529** | **8 blks / 40b** | **16 blks / 80b** | **2040b / 4080b** | **TRUE / TRUE** | **FAILED / FAILED** | **SELECTED (Shared 4-bit)** |
| **Candidate B** | $\text{BCH}(511, 19, 116, 233)$ | 0.03718 | 4 blks / 44b | 8 blks / 88b | 2044b / 4088b | TRUE / TRUE | FAILED / FAILED | Larger block size, marginal rate gain |
| **Candidate C** | $\text{BCH}(1023, 36, 222, 445)$ | 0.03519 | 2 blks / 46b | 4 blks / 92b | 2046b / 4092b | TRUE / TRUE | EXACT / FAILED | Leaks `quant_4bit` to Eve |

**Selection Rationale for Candidate A ($\text{BCH}(255, 9, 63)$)**:
1. **Minimal Block Size for $k > 1$**: $n=255$ is the smallest block length achieving $k > 1$ ($k=9$) while guaranteeing correction of all channel errors ($t=63 \ge 62$).
2. **Exact Bob Recovery**: Achieves 100% KAR and `exact_recovery = True` across both `quant_4bit` (8 blocks) and `prbs_4bit` (16 blocks).
3. **Eve Ordinary Decoding Outcomes**: In contrast to the $k=1$ baseline where Eve achieved 100% exact bitstream recovery under ordinary decoding, $\text{BCH}(255, 9, 63)$ results in ordinary-decoder failure (`Exact Recovery = False`) across both 4-bit paths due to detected syndrome decoding failures (`quant_4bit`: 3 failure blocks on Eve1, 1 on Eve2; `prbs_4bit`: 9 failure blocks on both Eve streams).
4. **Improved Code Rate**: Code rate $k/n = 9/255 \approx 0.03529$ represents a $4.5\times$ increase over $k=1$ ($1/127 \approx 0.00787$).
5. **Compact Helper Data & Padding**: Minimal padding overhead (40 bits for `quant_4bit`, 80 bits for `prbs_4bit`).

#### Four-Path Reconciliation Results ($N=500$, `data_kind=dummy`)

> [!NOTE]
> **Milestone Status**: **Experimental Reconciliation Milestone with Demonstrated Public-Helper Recovery on Tested Dummy Data**.
> Downstream stages (Privacy Amplification using bit-level SHA-256, NIST SP 800-22 Rev. 1a statistical testing, and Key Generation Rate) remain intentionally paused.

Information reconciliation routes parameters per path family via ReconciliationConfig:
- **2-bit paths (quant_2bit, prbs_2bit)**: $\text{BCH}(511, 1, 198)$ with designed distance  = 397$.
- **4-bit paths (quant_4bit, prbs_4bit)**: $\text{BCH}(255, 9, 62)$ with designed distance  = 125$.
- **Interleaving**: Strictly OFF (sequential blocks, trailing zero-padding).

##### Legitimate Channel Reconciliation (Alice–Bob)
Max observed per-block error counts on dummy data are derived from actual code execution (=198$ for =511$, =62$ for =255$):

| Path | Payload Bits | Configured Code (, k, t, d$) | Code Rate (/n$) | Blocks | Pad Bits | Max Error / Block ($\le t$) | Pre-KAR | Post-KAR | Exact Recovery | Blocks (S/F/M) | Independent Parity Constraints |
| :--- | :---: | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **quant_2bit** | 1,000 | **BCH(511, 1, 198, d=397)** | 0.00196 | 2 | 22 | **111** ($\le 198$) | 80.40% | **100.00%** | **TRUE** | 2 / 0 / 0 | 510 constraints (-k=510$) |
| **quant_4bit** | 2,000 | **BCH(255, 9, 62, d=125)** | 0.03529 | 8 | 40 | **42** ($\le 62$) | 90.20% | **100.00%** | **TRUE** | 8 / 0 / 0 | 246 constraints (-k=246$) |
| **prbs_2bit** | 4,000 | **BCH(511, 1, 198, d=397)** | 0.00196 | 8 | 88 | **198** ($\le 198$) | 75.85% | **100.00%** | **TRUE** | 8 / 0 / 0 | 510 constraints (-k=510$) |
| **prbs_4bit** | 4,000 | **BCH(255, 9, 62, d=125)** | 0.03529 | 16 | 80 | **62** ($\le 62$) | 86.20% | **100.00%** | **TRUE** | 16 / 0 / 0 | 246 constraints (-k=246$) |

*(Note on Error Coverage: Under the calibrated multi-path architecture, BCH(511, 1, 198) handles error counts up to 111 on quant_2bit (2 blocks, 22 pad bits) and up to 198 on prbs_2bit (8 blocks, 88 pad bits). For 4-bit paths, BCH(255, 9, 62) handles error counts up to 42 on quant_4bit and up to 62 on prbs_4bit.)*

##### Eavesdropper Performance Under Source-Specific Helper Data (Alice–Eve1-Alice & Bob–Eve1-Bob)
In accordance with established physical measurement comparisons (correlation, filtering, quantization, and PRBS):
- **Alice–Bob**: Alice is the source/reference; Bob is the legitimate receiver. Alice generates helper data  = A \oplus C_A$.
- **Alice–Eve1-Alice**: Alice is the source/reference; Eve1-Alice is the passive observer overhearing Alice's transmission. Eve1-Alice decodes against Alice's public helper data $.
- **Bob–Eve1-Bob**: Bob is the source/reference; Eve1-Bob is the passive observer overhearing Bob's transmission. Eve1-Bob decodes against Bob's separate helper data  = B \oplus C_B$ generated independently from Bob's bitstream.

*(Note: Bob being the reference for Bob–Eve1-Bob does NOT imply an interactive Bob–Eve communication session; Eve remains a passive eavesdropper in an offline measurement comparison).*

We explicitly separate **ordinary-decoder performance**, **bit agreement (post-KAR)**, and **public-helper enumeration recovery**:

| Path | Eavesdropper Pair | Reference / Source | Configured Code | Pre-KAR | Ordinary Post-KAR | Ordinary Decoder Exact Recovery | Blocks (S/F/M) | Public-Helper Enumeration Recovery |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| quant_2bit | Alice–Eve1-Alice | Alice | BCH(511, 1, 198, d=397) | 58.20% | **58.20%** | **FALSE** | 0 / 2 / 0 | Unverified |
| quant_2bit | Bob–Eve1-Bob | Bob | BCH(511, 1, 198, d=397) | 55.40% | **55.40%** | **FALSE** | 0 / 2 / 0 | Unverified |
| quant_4bit | Alice–Eve1-Alice | Alice | BCH(255, 9, 62, d=125) | 79.10% | **89.60%** | **FALSE** | 5 / 3 / 0 | **100% (0 ambiguity)** |
| quant_4bit | Bob–Eve1-Bob | Bob | BCH(255, 9, 62, d=125) | 77.70% | **89.50%** | **FALSE** | 5 / 3 / 0 | **100% (0 ambiguity)** |
| prbs_2bit | Alice–Eve1-Alice | Alice | BCH(511, 1, 198, d=397) | 56.10% | **69.42%** | **FALSE** | 3 / 5 / 0 | Unverified |
| prbs_2bit | Bob–Eve1-Bob | Bob | BCH(511, 1, 198, d=397) | 56.38% | **60.92%** | **FALSE** | 1 / 7 / 0 | Unverified |
| prbs_4bit | Alice–Eve1-Alice | Alice | BCH(255, 9, 62, d=125) | 73.25% | **81.85%** | **FALSE** | 7 / 9 / 0 | **100% (0 ambiguity)** |
| prbs_4bit | Bob–Eve1-Bob | Bob | BCH(255, 9, 62, d=125) | 72.45% | **81.58%** | **FALSE** | 7 / 9 / 0 | **100% (0 ambiguity)** |

> [!CAUTION]
> **Critical Distinctions in Eavesdropper Recovery Metrics**:
> 1. **Ordinary Decoder Failure $\ne$ 0% Recovered Bits**:
>    `Exact Recovery = False` indicates only that Eve's ordinary bounded syndrome decoder failed to achieve 100% bitwise recovery across all blocks due to detected decoding failures or miscorrections. It does **NOT** mean Eve recovers 0% of the bits; in fact, Eve retains **61.90% to 96.35% bit agreement** with Alice after ordinary decoding.
> 2. **Candidate Enumeration vs. Verified Unique Recovery**:
>    Having a small code space (e.g. $k=1 \implies 2$ codewords, or $k=9 \implies 512$ codewords) enables fast exhaustive enumeration ($<0.1$ s), but candidate enumeration alone does not prove immediate unique bitstream recovery. For unique recovery, the attacker must additionally possess sufficiently independent constraints (e.g. public padding columns or fixed alphabet structure) whose constraint submatrix has full row rank over $\text{GF}(2)$ to collapse all candidate ambiguity down to a single solution.
>    - **Demonstrated Recovery Scope**: On the tested 4-bit dummy dataset (`quant_4bit` and `prbs_4bit` under $\text{BCH}(255, 9, 62)$ and $\text{BCH}(255, 9, 63)$), the combination of 40 trailing zero-padding columns ($\text{rank}=9$) and the publicly known 3-level quantizer/PRBS alphabet was empirically verified to collapse all 512 candidates down to **exactly 1 surviving candidate per block** (100% ground-truth bitstream recovery with 0 unresolved ambiguity).
>    - **Unverified Scope**: On 2-bit paths under $k=1$, although there are only 2 codewords per block, full-stream unique recovery via public-helper enumeration has not been empirically verified across all blocks, so candidate enumeration on 2-bit paths remains classified as *Unverified*.
> 3. **Cryptographic Secrecy Finding & Impossibility of Restoration via Hashing**:
>    Neither small dimension $k$ nor ordinary-decoder failure establishes cryptographic secrecy. Where Eve uniquely reconstructs Alice's entire unpadded bitstream $A$ from public helper data and public constraints alone, **hashing a fully recovered input cannot restore secrecy**.
>    Whether privacy amplification employs the repository's historical bit-level SHA-256 implementation (PA.pdf Section 3.2.6, Equations 3.37–3.53) or universal hashing with a publicly broadcast seed, evaluating any deterministic public hash function on a known input $A$ produces a digest $K = \text{Hash}(A)$ that Eve computes identically. Secrecy can only be established if physical entropy remains unobserved and helper data leakage does not span the entire input entropy.

> [!IMPORTANT]
> **Paused Downstream Evaluation Notice**:
> Downstream stages (**Privacy Amplification via SHA-256**, **NIST SP 800-22 Rev. 1a statistical randomness testing**, and **Key Generation Rate**) have **not been recalculated or re-evaluated** following this BCH measurement comparison pairing correction (Bob–Eve1-Bob with independent Bob helper data). All downstream components remain strictly paused until explicitly requested. Historical PA, NIST, and KGR metrics in documentation reflect earlier exploratory runs.

### 3. Direct Bitstream Equality and Receiver Isolation
- **Direct Bitstream Equality**: BCH reconciliation success is defined strictly by bitwise equality between the source unpadded bitstream $A$ and receiver unpadded recovered bitstream $\hat{A}$ (`exact_recovery = bool(source_bits == recovered_bits)`).
- **Strict Receiver Isolation**: The receiver decoding pipeline accesses only the receiver's own observed bits $B$, the public helper data $H$, and code parameters $(n, k, t)$. Alice's source bits are never accessible during decoding.
- **Failed-Block Fallback Convention**: When a detected decoding failure occurs (syndrome equations cannot be solved within error-correction radius $t$), unchanged raw receiver bits are retained as fallback (never discarded or zeroed). When any block fails or is miscorrected, unpadded bitstream recovery is incomplete (`exact_recovery = False`). Channel errors beyond $t$ result in either a detected decoding failure or a miscorrection (the decoder does not have access to the true channel error count).

> [!WARNING]
> **Information-Theoretic Security Boundaries**:
> 1. **PRBS Entropy**: LFSR bit expansion is deterministic and contributes **0 bits of physical source entropy**.
> 2. **Helper Data Leakage**: The public broadcast of $H = A \oplus C$ reveals linear parity constraints, leaking up to $n - k$ bits of information about $A$ per block.
> 3. **Decoder Failure != Secrecy**: Standard Eve decoder failure (0% recovery) does not imply confidentiality; without interleaving, known padding reveals Block 1 of `prbs_2bit`, and combining this with PRBS parity constraints recovers Alice's full bitstream algebraically.

---

## Privacy Amplification Stage (PA.pdf Section 3.2.6, Equations 3.37–3.53)

Governed by `PA.pdf` **Section 3.2.6, Equations (3.37)–(3.53), pages 30–33** and **FIPS PUB 180-4**:

Privacy Amplification compresses consecutive, non-overlapping 100-bit segments of the unpadded reconciled bitstream into 256-bit secret keys via the cryptographic hash function SHA-256. While SHA-256 expands residual bit errors under ordinary decoding across the key space via cryptographic diffusion (the avalanche effect), it does not increase physical min-entropy or prevent an algebraic attacker from computing the identical key if the source bitstream is solved from public helper data.

### 1. 100-Bit Consecutive Non-Overlapping Segmentation
Unpadded reconciled bitstreams from BCH reconciliation are divided into consecutive, non-overlapping segments of $L_{\text{chunk}} = 100$ bits, preserving temporal order:
```math
S_c = M[100c : 100(c + 1)], \qquad c \in \{0, \dots, M_{\text{chunks}} - 1\}
```
- **Dynamic Chunk Count Derivation**: $M_{\text{chunks}} = L_{\text{total}} / 100$.
- **Explicit Incomplete Segment Rejection**: Bitstream length must be an exact positive multiple of 100 bits. Incomplete trailing segments are strictly rejected (never silently truncated or padded).
- **Four Supported Paths and Derived Key Counts**:
  - `quant_2bit`: 1,000 bits $\to$ **10 keys** of 256 bits each.
  - `quant_4bit`: 2,000 bits $\to$ **20 keys** of 256 bits each.
  - `prbs_2bit`: 4,000 bits $\to$ **40 keys** of 256 bits each.
  - `prbs_4bit`: 4,000 bits $\to$ **40 keys** of 256 bits each.

### 2. Bit-Level SHA-256 Padding per Segment (Equations 3.37–3.39)
Unlike conventional byte-oriented hash interfaces, the mathematical specification operates directly at the bit level on arbitrary bit lengths. Each 100-bit segment ($L = 100$) is independently padded:

```math
S'_c = S_c \parallel 1 \parallel 0^p \parallel [100]_{64}
```
where $p$ is the smallest non-negative integer satisfying:
```math
100 + 1 + p \equiv 448 \pmod{512} \implies p = (448 - 1 - 100) \bmod 512 = 347 \text{ bits}
```
and $[100]_{64}$ is the 64-bit big-endian representation of integer 100. The total padded length $|S'_c| = 100 + 1 + 347 + 64 = 512$ bits (exactly 1 block of 512 bits).

### 3. Message Scheduling & 64-Round Compression (Equations 3.40–3.53)
Each 512-bit block $M^{(i)}$ is partitioned into 16 32-bit words $W_0 \dots W_{15}$. Words $W_{16} \dots W_{63}$ are expanded via:
```math
W_t = \sigma_1(W_{t-2}) + W_{t-7} + \sigma_0(W_{t-15}) + W_{t-16} \pmod{2^{32}}
```
where $\sigma_0(x) = \text{ROTR}^7(x) \oplus \text{ROTR}^{18}(x) \oplus \text{SHR}^3(x)$ and $\sigma_1(x) = \text{ROTR}^{17}(x) \oplus \text{ROTR}^{19}(x) \oplus \text{SHR}^{10}(x)$.

The 64-round compression updates eight 32-bit state registers $(a, b, c, d, e, f, g, h)$ from the initial hash values $H^{(0)}$ using the non-linear functions $\text{Ch}(e, f, g)$, $\text{Maj}(a, b, c)$, and the rotation sums $\Sigma_0(a)$ and $\Sigma_1(e)$. Each 100-bit segment independently yields one 256-bit secret key digest:
```math
K_c = H_0 \parallel H_1 \parallel \dots \parallel H_7 \in \{0, 1\}^{256}
```

### 4. Per-Chunk Key Agreement Rate (KAR) & Summary Aggregation per Equation (3.64)
Evaluated strictly per `PA.pdf` Section 3.2.8.c, Equation (3.64) for each chunk $c$:
```math
\text{KAR}_c = \left(1 - \frac{N_{\text{mismatch}, c}}{256}\right) \times 100\% = \frac{256 - N_{\text{mismatch}, c}}{256} \times 100\%
```
where $N_{\text{mismatch}, c} = \sum_{j=0}^{255} (K_{\text{source}, c}[j] \ne K_{\text{receiver}, c}[j])$. Exact key match for a chunk requires bitwise equality across all 256 bits: `exact_key_match_c = (K_source_c == K_receiver_c)`.

Aggregated summary metrics report the mean post-PA KAR across all chunks, total matching chunk count, and overall exact match status.

### 5. Four-Path Segmented Privacy Amplification Results (Dummy Dataset, N = 500)
- **Supported Paths**: `quant_2bit` (10 keys), `quant_4bit` (20 keys), `prbs_2bit` (40 keys), `prbs_4bit` (40 keys).
- **All 4 Channels Independently Processed with Channel Isolation**: Alice, Bob, Eve1-Alice, Eve1-Bob.
- **Bidirectional Transmission Observation Model**:
  1. `Alice–Bob`: Legitimate communication pair (Alice reference vs Bob receiver, using Alice helper data).
  2. `Alice–Eve1-Alice`: Passive eavesdropper overhearing Alice (Alice reference vs Eve1-Alice receiver, using Alice helper data).
  3. `Bob–Eve1-Bob`: Passive eavesdropper overhearing Bob (Bob reference vs Eve1-Bob receiver, using Bob helper data).

| Path | Evaluation Pair | Reference / Source | Receiver | Chunks | Pre-PA KAR | Post-PA Mean KAR | Δ (pp) | Exact Matches | Match Rate | All Match |
| :--- | :--- | :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `quant_2bit` | **Alice–Bob** | Alice | Bob | 10 | 100.00% | **100.00%** | +0.00 pp | **10 / 10** | **100.0%** | **TRUE (MATCH)** |
| `quant_2bit` | Alice–Eve1-Alice | Alice | Eve1-Alice | 10 | 58.20% | 50.47% | -7.73 pp | 0 / 10 | 0.0% | FALSE (MISMATCH) |
| `quant_2bit` | Bob–Eve1-Bob | Bob | Eve1-Bob | 10 | 55.40% | 49.18% | -6.22 pp | 0 / 10 | 0.0% | FALSE (MISMATCH) |
| `quant_4bit` | **Alice–Bob** | Alice | Bob | 20 | 100.00% | **100.00%** | +0.00 pp | **20 / 20** | **100.0%** | **TRUE (MATCH)** |
| `quant_4bit` | Alice–Eve1-Alice | Alice | Eve1-Alice | 20 | 89.60% | 80.43% | -9.17 pp | 12 / 20 | 60.0% | FALSE (MISMATCH) |
| `quant_4bit` | Bob–Eve1-Bob | Bob | Eve1-Bob | 20 | 89.50% | 50.16% | -39.34 pp | 0 / 20 | 0.0% | FALSE (MISMATCH) |
| `prbs_2bit` | **Alice–Bob** | Alice | Bob | 40 | 100.00% | **100.00%** | +0.00 pp | **40 / 40** | **100.0%** | **TRUE (MATCH)** |
| `prbs_2bit` | Alice–Eve1-Alice | Alice | Eve1-Alice | 40 | 69.42% | 68.59% | -0.83 pp | 15 / 40 | 37.5% | FALSE (MISMATCH) |
| `prbs_2bit` | Bob–Eve1-Bob | Bob | Eve1-Bob | 40 | 60.92% | 51.98% | -8.94 pp | 2 / 40 | 5.0% | FALSE (MISMATCH) |
| `prbs_4bit` | **Alice–Bob** | Alice | Bob | 40 | 100.00% | **100.00%** | +0.00 pp | **40 / 40** | **100.0%** | **TRUE (MATCH)** |
| `prbs_4bit` | Alice–Eve1-Alice | Alice | Eve1-Alice | 40 | 81.85% | 69.75% | -12.10 pp | 16 / 40 | 40.0% | FALSE (MISMATCH) |
| `prbs_4bit` | Bob–Eve1-Bob | Bob | Eve1-Bob | 40 | 81.58% | 53.52% | -28.06 pp | 3 / 40 | 7.5% | FALSE (MISMATCH) |

*(Historical note: Earlier exploratory single-digest 2-bit PA runs without segmentation and superseded single-Alice-reference descriptions for Bob–Eve1-Bob are replaced by this 100-bit segmented multi-key architecture aligned with bidirectional transmission observation).*

#### Derived Channel Secret Keys (First Chunk Hex Digests & Total Chunks):
| Path | Channel | Role | Total Chunks | First Chunk SHA-256 Hex Digest (64 characters) |
| :--- | :--- | :--- | :---: | :--- |
| `quant_2bit` | Alice | Legitimate Source (Reference Key) | 10 | `f247b276231d0a1b890d4a944ec7dbe8ef7ae3fc2a2efb5c544bcdd124c3848d` |
| `quant_2bit` | Bob | Legitimate Receiver (Reconciled to Alice) | 10 | `f247b276231d0a1b890d4a944ec7dbe8ef7ae3fc2a2efb5c544bcdd124c3848d` |
| `quant_2bit` | Eve1-Alice | Passive Eavesdropper (Overhearing Alice) | 10 | `64104aafa74db0084a7b0e63ad27d2b91419f05da7b7b2addaf5c16d4d87aaed` |
| `quant_2bit` | Eve1-Bob | Passive Eavesdropper (Overhearing Bob) | 10 | `fa4622a5553cede860ffd0190a8b0bebcd4f744ceceedf1b59e79074e9fecbbd` |
| `quant_4bit` | Alice | Legitimate Source (Reference Key) | 20 | `7fc45c39d8232ae32cce944d32984db60a5917830334322478988ed7b6b53801` |
| `quant_4bit` | Bob | Legitimate Receiver (Reconciled to Alice) | 20 | `7fc45c39d8232ae32cce944d32984db60a5917830334322478988ed7b6b53801` |
| `quant_4bit` | Eve1-Alice | Passive Eavesdropper (Overhearing Alice) | 20 | `7fc45c39d8232ae32cce944d32984db60a5917830334322478988ed7b6b53801` |
| `quant_4bit` | Eve1-Bob | Passive Eavesdropper (Overhearing Bob) | 20 | `cf08b79275e26f01a53c3becd0c78f6c5d348f3b41a0cffc3720dfc8f9409191` |
| `prbs_2bit` | Alice | Legitimate Source (Reference Key) | 40 | `7d47f268d16798ebf1b62bcd21f07d9bcf1cf55844ad113e9301417b493a9c8d` |
| `prbs_2bit` | Bob | Legitimate Receiver (Reconciled to Alice) | 40 | `7d47f268d16798ebf1b62bcd21f07d9bcf1cf55844ad113e9301417b493a9c8d` |
| `prbs_2bit` | Eve1-Alice | Passive Eavesdropper (Overhearing Alice) | 40 | `7d47f268d16798ebf1b62bcd21f07d9bcf1cf55844ad113e9301417b493a9c8d` |
| `prbs_2bit` | Eve1-Bob | Passive Eavesdropper (Overhearing Bob) | 40 | `7d47f268d16798ebf1b62bcd21f07d9bcf1cf55844ad113e9301417b493a9c8d` |
| `prbs_4bit` | Alice | Legitimate Source (Reference Key) | 40 | `a150d2fe866a116d191ff0035213261458e6e3483be89d7f222ae3c714e29d8e` |
| `prbs_4bit` | Bob | Legitimate Receiver (Reconciled to Alice) | 40 | `a150d2fe866a116d191ff0035213261458e6e3483be89d7f222ae3c714e29d8e` |
| `prbs_4bit` | Eve1-Alice | Passive Eavesdropper (Overhearing Alice) | 40 | `1a30a2b69c18a6db21bb6cee106ecd7763ba2ad49ecde8616054392778dc1375` |
| `prbs_4bit` | Eve1-Bob | Passive Eavesdropper (Overhearing Bob) | 40 | `a150d2fe866a116d191ff0035213261458e6e3483be89d7f222ae3c714e29d8e` |

> [!CAUTION]
> **Scientific Secrecy Disclaimer**:
> Synthetic software validation only; 256-bit SHA-256 output **does NOT imply 256 bits of physical entropy** when upstream PRBS expansion is deterministic and public BCH helper data leaks parity relations. Where Eve reconstructs the unpadded source segment, hashing that segment produces the identical 256-bit digest. Physical channel probing is postponed.

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
The test suite comprises 119 automated unit and integration tests across 10 test modules:

```powershell
# Run all unit tests (119 tests)
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

#### D. Full Execution with MSHKF Filtering, Modified ADQ, and PRBS Expansion Stages
Run the CLI with `--prbs` (which automatically invokes `--quantize` and `--filter` prerequisites when omitted) to generate all sample-level PRBS expansions, concatenated bitstreams, before/after KAR metrics, companion multi-sheet Excel workbook, and the 2×2 PRBS KAR visualization figure:
```powershell
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --quantize `
  --prbs `
  --prbs-samples-output "outputs/dummy_rssi_prbs_samples.csv" `
  --prbs-bitstreams-output "outputs/dummy_rssi_prbs_bitstreams.csv" `
  --prbs-metrics-output "outputs/dummy_rssi_prbs_metrics.csv" `
  --prbs-config-output "outputs/dummy_rssi_prbs_config.json" `
  --prbs-xlsx-output "outputs/dummy_rssi_prbs.xlsx" `
  --prbs-figure-prefix "outputs/dummy_rssi_prbs_kar"
```

#### E. Full Execution through Global BCH Information Reconciliation
Run the CLI with `--reconcile` (which automatically triggers prerequisite filtering, quantization, and PRBS stages) to perform codeword-based BCH information reconciliation:
```powershell
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --quantize `
  --prbs `
  --reconcile `
  --reconcile-metrics-output "outputs/dummy_rssi_bch_metrics.csv" `
  --reconcile-blocks-output "outputs/dummy_rssi_bch_blocks.csv" `
  --reconcile-config-output "outputs/dummy_rssi_bch_config.json" `
  --reconciled-xlsx-output "outputs/dummy_rssi_bch.xlsx" `
  --reconcile-figure-prefix "outputs/dummy_rssi_bch_reconciliation"
```

#### F. Full Execution through Privacy Amplification (SHA-256 Key Derivation)
Run the CLI with `--privacy-amplify` (or `--pa`), which automatically executes all prerequisite stages (filtering, quantization, PRBS, and BCH reconciliation) to produce fixed 256-bit secret keys:
```powershell
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --quantize `
  --prbs `
  --reconcile `
  --privacy-amplify `
  --pa-metrics-output "outputs/dummy_rssi_pa_metrics.csv" `
  --pa-keys-output "outputs/dummy_rssi_pa_keys.csv" `
  --pa-config-output "outputs/dummy_rssi_pa_config.json" `
  --pa-xlsx-output "outputs/dummy_rssi_pa.xlsx" `
  --pa-figure-prefix "outputs/dummy_rssi_pa_comparison"
```

> [!IMPORTANT]
> **Unified Pipeline Architecture & Candidate Key Flags**:
> - **Prerequisite Chaining**: `--privacy-amplify` automatically enables `--reconcile`, `--prbs`, `--quantize`, and `--filter`.
> - **Candidate Key Outputs**: Candidate keys can be exported using `--pa-keys-output` (or `--reconcile-keys-output` when reconciliation / privacy amplification is active).
> - **Obsolete Flags Rejected**: Passing `--reconcile-shared` or `--reconcile-mode` will raise an actionable error directing users to standard execution.

##### Two-Path Experimental Results (Dummy Dataset, N = 500):
| Path | Evaluation Pair | Pre-BCH KAR | Post-BCH KAR | Δ (pp) | Blocks (Succ/Fail/Mis) | Block Success Rate | Exact Recovery |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| `quant_2bit` | Alice–Bob (Legitimate) | 80.40% | 100.00% | +19.60 pp | 1 / 0 / 0 | 100.0% | **TRUE** |
| `quant_2bit` | Alice–Eve1-Alice (Eve Stream 1) | 58.20% | 58.20% | +0.00 pp | 0 / 1 / 0 | 0.0% | **FALSE** |
| `quant_2bit` | Alice–Eve1-Bob (Eve Stream 2) | 57.80% | 57.80% | +0.00 pp | 0 / 1 / 0 | 0.0% | **FALSE** |
| `prbs_2bit` | Alice–Bob (Legitimate) | 76.27% | 100.00% | +23.73 pp | 2 / 0 / 0 | 100.0% | **TRUE** |
| `prbs_2bit` | Alice–Eve1-Alice (Eve Stream 1) | 56.53% | 68.93% | +12.40 pp | 1 / 1 / 0 | 50.0% | **FALSE** |
| `prbs_2bit` | Alice–Eve1-Bob (Eve Stream 2) | 55.87% | 55.87% | +0.00 pp | 0 / 2 / 0 | 0.0% | **FALSE** |

##### Methodological Conventions & Scientific Constraints:
1. **Zero-Padding & Payload KAR**:
   - `quant_2bit`: Raw length = 1,000 bits $\to$ 1 block of $n=1023$ (23 pad bits excluded from payload KAR).
   - `prbs_2bit`: Raw length = 1,500 bits $\to$ 2 blocks of $n=1023$ (total 2,046 bits; 546 pad bits excluded from payload KAR).
2. **Failed-Block Convention & Decoding Outcomes**:
   - When a detected decoding failure occurs, unchanged raw receiver bits are retained as fallback (never discarded or zeroed).
   - When any block fails or is miscorrected, receiver unpadded bitstream recovery is incomplete (`exact_recovery = False`).
   - Channel errors beyond $t$ lead to either a detected decoding failure or an undetected miscorrection, as the decoder operates strictly on syndromes and does not have access to the true channel error count.
3. **Eve Ordinary Decoding vs. Public-Information Algebraic Attack**:
   - Standard BCH decoding by Eve largely fails (0% block recovery on `quant_2bit`, 0% for `Bob–Eve1-Bob`, and failure on Block 0 for `Alice–Eve1-Alice`).
   - However, **decoder failure does NOT establish secrecy**.
   - Without interleaving, known padding reveals the final PRBS block; the reported full-stream attack additionally uses per-sample PRBS parity constraints.
   - Together, the joint $\text{GF}(2)$ linear system achieves **full rank** (92/92 for `prbs_2bit`, unique affine candidate for `quant_2bit`), allowing an algebraic attacker to recover Alice's full bitstream with 100% accuracy without channel observation.
4. **Mandatory Scientific Disclaimer**:
   > **Dummy-data comparison; global configuration has reported public-information leakage. KAR does not establish secrecy.**
   > This configuration is strictly for algorithmic benchmarking and comparative analysis; it is **NOT** claimed to be cryptographically secure.

##### Visualization Artifacts:
- `outputs/dummy_rssi_reconciliation.png` (300-dpi raster) & `outputs/dummy_rssi_reconciliation.pdf` (vector):
  - **Panel (a)**: `quant_2bit` Pre-BCH vs Post-BCH KAR across all three evaluation pairs with signed percentage-point changes ($\Delta\text{ pp}$).
  - **Panel (b)**: `quant_4bit` Pre-BCH vs Post-BCH KAR across all three evaluation pairs.
  - **Panel (c)**: `prbs_2bit` Pre-BCH vs Post-BCH KAR across all three evaluation pairs.
  - **Panel (d)**: `prbs_4bit` Pre-BCH vs Post-BCH KAR across all three evaluation pairs.
  - **Panel (e)**: Exact block recovery rates (decoder success %) across all four paths for legitimate and eavesdropper channels.
  - **Panel (f)**: Quantitative summary table (Failures, Miscorrections, Exact Recovery) and scientific constraint notes box. All parameters dynamically reflect 2-bit $\text{BCH}(127,1,62)$ and 4-bit $\text{BCH}(255,9,63)$.
- `outputs/dummy_rssi_pa_comparison.png` (300-dpi raster) & `outputs/dummy_rssi_pa_comparison.pdf` (vector):
  - **Panel (a)**: `quant_2bit` Pre-PA vs Post-PA KAR across Alice–Bob, Alice–Eve1-Alice, Alice–Eve1-Bob.
  - **Panel (b)**: `prbs_2bit` Pre-PA vs Post-PA KAR across Alice–Bob, Alice–Eve1-Alice, Alice–Eve1-Bob.
  - **Panel (c)**: Final secret key KAR & avalanche isolation (100% legitimate match vs ~50% eavesdropper KAR with exact match flags).
  - **Panel (d)**: Quantitative summary table & scientific disclaimer box.

> [!TIP]
> **Microsoft Excel Guidance for Leading Zeros (`00` vs `0`, `01` vs `1`, 256-bit keys)**:
> - The raw CSV exports (`outputs/dummy_rssi_quantized_samples.csv`, `outputs/dummy_rssi_prbs_samples.csv`, `outputs/dummy_rssi_reconcile_blocks.csv`, and `outputs/dummy_rssi_pa_keys.csv`) preserve exact string literals. However, Microsoft Excel automatically strips leading zeros when directly double-clicking a CSV file.
> - **Excel users should open the companion XLSX workbooks** (`outputs/dummy_rssi_quantized.xlsx`, `outputs/dummy_rssi_prbs.xlsx`, `outputs/dummy_rssi_bch.xlsx`, and `outputs/dummy_rssi_pa.xlsx`) instead of the CSVs. All bitstreams and keys are stored explicitly as Text cells (`@`), preserving leading zeros across all spreadsheet viewers.

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
- `outputs/dummy_rssi_quantization.png` & `.pdf`: High-resolution (300 dpi) and vector PDF quantization KAR comparison figure.
- `outputs/dummy_rssi_prbs_samples.csv`: Per-sample PRBS expansion details (sample index, level, original encoding, seed integer, expanded bits, zero-state status, actual period) for all 4 channels.
- `outputs/dummy_rssi_prbs_bitstreams.csv`: Concatenated PRBS bitstreams for 2-bit (4,000 bits) and 4-bit (4,000 bits) paths per channel.
- `outputs/dummy_rssi_prbs_metrics.csv`: Pre- vs. post-PRBS KAR comparison metrics and agreement rates across Alice–Bob, Alice–Eve1-Alice, and Bob–Eve1-Bob.
- `outputs/dummy_rssi_prbs_config.json`: PRBS configuration metadata, polynomial details, zero-seed counts, and implementation choices.
- `outputs/dummy_rssi_prbs.xlsx`: Companion multi-sheet Excel workbook (`PRBS Samples`, `PRBS Bitstreams`, `KAR Comparison`, `Configuration & Zero Seeds`) with explicit Text formatting and >32k cell chunking.
- `outputs/dummy_rssi_prbs_kar.png` & `.pdf`: High-resolution (300 dpi) and vector PDF 2×2 PRBS KAR visualization figure.
- `outputs/dummy_rssi_bch_metrics.csv`: Summary metrics table (Pre-KAR, Post-KAR, exact recovery, detected failures, miscorrections, helper overhead) across evaluated pairs for all four paths (`quant_2bit`, `quant_4bit`, `prbs_2bit`, `prbs_4bit`).
- `outputs/dummy_rssi_bch_blocks.csv`: Per-block reconciliation details (block index, bit lengths, padding, Alice/Bob/Eve bit slices, error counts, correction status, receiver equality).
- `outputs/dummy_rssi_bch_config.json`: Reconciliation metadata, algorithm specification, and BCH code parameters.
- `outputs/dummy_rssi_bch.xlsx`: Companion multi-sheet Excel workbook (`Reconciliation Metrics`, `Block Details`, `Recovered Bitstreams`) preserving leading zeros.
- `outputs/dummy_rssi_reconciliation.png` & `.pdf`: High-resolution (300 dpi) and vector PDF 4-path reconciliation visualization figure.
- `outputs/dummy_rssi_pa_metrics.csv`: Privacy amplification metrics (Pre-PA KAR, Post-PA KAR, Delta pp, exact key match, mismatched bits) across 2 paths × 3 pairs.
- `outputs/dummy_rssi_pa_keys.csv`: Channel secret keys table containing 256-character binary strings and 64-character hex digests across all channels.
- `outputs/dummy_rssi_pa_config.json`: Privacy amplification configuration metadata, FIPS 180-4 references, and pair summary results.
- `outputs/dummy_rssi_pa.xlsx`: Companion multi-sheet Excel workbook (`PA Metrics`, `Channel Keys`, `Config & Disclaimers`) with explicit Text formatting `@`.
- `outputs/dummy_rssi_pa_comparison.png` & `.pdf`: High-resolution (300 dpi) and vector PDF 2×2 Privacy Amplification KAR comparison figures.
- `outputs/nist_metrics.csv`: NIST SP 800-22 test statistics, p-values, applicability, and pass/fail for all derived 256-bit keys across both paths.
- `outputs/nist_config.json`: NIST configuration metadata, significance level $\alpha=0.01$, and ApEn block length $m=2$.
- `outputs/kgr_metrics.csv`: Key Generation Rate metrics table reporting raw bits, accepted bits, elapsed software duration ($T$), raw KGR (bps), accepted KGR (bps), and Alice–Bob key agreement.
- `outputs/kgr_config.json`: KGR configuration metadata, monotonic timer boundaries, and cold-start BCH JIT cache policy.
- `outputs/evaluation_summary.xlsx`: Companion multi-sheet Excel workbook (`KGR Metrics`, `NIST Randomness`, `Config & Disclaimers`) with explicit Text formatting `@` for 256-bit hex digests.
- *(Historical artifacts preserved)*: `outputs/dummy_rssi_reconcile_*` and `outputs/dummy_rssi_shared_bch_*` remain in `outputs/` for historical auditability.

---

## Methodological Limitations & Warnings

The results of this analysis are strictly for **software validation** using synthetic dummy data. The resulting correlation coefficients and Key Agreement Rates **must not be used to draw empirical security conclusions or characterize real physical channel propagation**, as physical channel probing is postponed, not replaced. Parameters such as $W=50$ and $\alpha=0.5$ are provisional software-validation settings, not optimized physical-channel parameters. Deterministic LFSR expansion does not add physical channel entropy. Public helper data reveals linear parity constraints and leaks up to $(n - k)$ bits per block.

Furthermore, passing the three NIST SP 800-22 tests (Monobit, Runs, Approximate Entropy) validates basic statistical randomness properties of the SHA-256 digests on dummy data, but does **not** claim a full NIST suite pass, physical entropy, or cryptographic unpredictability. Key Generation Rate (KGR) measures pure software processing throughput on a local computer with pre-warmed JIT caches; it does **not** represent an empirical over-the-air channel probing rate. Matching keys from Bob are never double-counted to inflate generated bit counts.
