# Project Progress & Handoff: RSSI-based Secret Key Generation (SKG)

## 1. Project Purpose & Methodological Reference
This research project develops a physical-layer Secret Key Generation (SKG) pipeline based on Received Signal Strength Indicator (RSSI) measurements.

The project currently implements eight sequential pipeline stages:
1. **RSSI Filtering Stage**: Modified Sage–Husa Adaptive Kalman Filter (MSHKF) based on **`PA.pdf`, Section 3.2.2, Equations (3.10)–(3.20), pages 26–27**.
2. **Zero-Lag Pearson Correlation Analysis**: As defined in **`PA.pdf`, Equation (3.62), page 34**:

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

3. **Modified Adaptive Dual-Threshold Quantization (MADQ)**: As defined in **`PA.pdf`, Section 3.2.3, Equations (3.21)–(3.23), pages 27–28**, with performance evaluation via Key Agreement Rate (KAR) in **`PA.pdf`, Section 3.2.8.c, Equation (3.64), page 35**:

```math
q_i^+ = \mu_X + \alpha \sigma_X \qquad (3.21)
```

```math
q_i^- = \mu_X - \alpha \sigma_X \qquad (3.22)
```

```math
Q(X_i) = \begin{cases}
0, & X_i < q_i^- \\
1, & q_i^- \le X_i \le q_i^+ \\
2, & X_i > q_i^+
\end{cases} \qquad (3.23)
```

```math
\text{KAR} = \left(1 - \frac{N_{\text{mismatch}}}{N_{\text{total}}}\right) \times 100\% = \frac{N_{\text{total}} - N_{\text{mismatch}}}{N_{\text{total}}} \times 100\% \qquad (3.64)
```

4. **PRBS Expansion Stage (Galois XOR-LFSR)**: Citing LFSR principles in **`PA.pdf`, Section 3.2.4 (pages 28–29)** as background (with characteristic polynomial Equation 3.24, output recurrence Equation 3.25, and period Equation 3.26):

```math
f(x) = c_m x^m + c_{m-1} x^{m-1} + \dots + c_1 x + c_0 \qquad (3.24)
```

**Output Recurrence (Equation 3.25)**:
```math
S_{i+m} = \left(\sum_{j=0}^{m-1} C_j S_{i+j}\right) \bmod 2 \qquad (3.25)
```

5. **BCH Codeword-based Information Reconciliation**: As defined in **`PA.pdf`, Section 3.2.5, Equations (3.32)–(3.36), pages 29–30**:

```math
H = A \oplus C \qquad (3.32)
```
```math
C' = H \oplus B = (A \oplus C) \oplus B = C \oplus (A \oplus B) = C \oplus e \qquad (3.33)
```
```math
\hat{C} = \text{BCH\_Decode}(C') \qquad (3.34)
```
```math
\hat{A} = H \oplus \hat{C} \qquad (3.35)
```
When decoding is successful and without miscorrection, $\hat{C} = C$ and $\hat{A} = A$. Reconciliation success is defined by direct unpadded bitstream equality:
```math
\text{exact\_recovery} = (A == \hat{A}_{\text{unpadded}})
```

6. **Privacy Amplification (Bit-Level SHA-256)**: As defined in **`PA.pdf`, Section 3.2.6, Equations (3.37)–(3.53), pages 30–33** and **FIPS PUB 180-4**:
```math
M' = M \parallel 1 \parallel 0^p \parallel [L]_{64}, \qquad p = (448 - 1 - L) \bmod 512
```
```math
K = \text{SHA256}(M') \in \{0, 1\}^{256}
```
Final Secret Key Agreement Rate (KAR) is evaluated strictly per **`PA.pdf` Section 3.2.8.c, Equation (3.64)**:
```math
\text{KAR} = \frac{256 - N_{\text{mismatch}}}{256} \times 100\%
```
```math
\text{exact\_key\_match} = (K_{\text{source}} == K_{\text{receiver}})
```

7. **Statistical Randomness Testing (NIST SP 800-22 Rev. 1a)**: Governed by **`PA.pdf`, Section 3.2.8.d, Equations (3.65)–(3.73), pages 35–37** and cross-checked against official **NIST SP 800-22 Rev. 1a**:
- **Frequency (Monobit) Test (Equations 3.65–3.66, NIST Sec 2.1)**:
  $$S_n = \sum_{i=1}^n (2\varepsilon_i - 1), \qquad s_{\text{obs}} = \frac{|S_n|}{\sqrt{n}}, \qquad P\text{-value} = \text{erfc}\left(\frac{s_{\text{obs}}}{\sqrt{2}}\right)$$
- **Runs Test (Equations 3.67–3.69, NIST Sec 2.3)**:
  $$\pi = \frac{1}{n}\sum_{i=1}^n \varepsilon_i, \qquad \tau = \frac{2}{\sqrt{n}}$$
  *Prerequisite Check*: If $|\pi - 0.5| \ge \tau$, the sequence is heavily unbalanced; test is marked not applicable, $P\text{-value} = 0.0$, and the explicit reason is recorded. If satisfied:
  $$V_n(\text{obs}) = 1 + \sum_{k=1}^{n-1} (\varepsilon_k \ne \varepsilon_{k+1}), \qquad P\text{-value} = \text{erfc}\left(\frac{|V_n(\text{obs}) - 2n\pi(1-\pi)|}{2\sqrt{2n}\pi(1-\pi)}\right)$$
- **Approximate Entropy Test (Equations 3.70–3.73, NIST Sec 2.12)**:
  $$C_i^{(k)} = \frac{\#i^{(k)}}{n}, \qquad \phi(k) = \sum_{i=0}^{2^k - 1} C_i^{(k)} \ln C_i^{(k)} \qquad (\text{with convention } 0 \ln 0 = 0)$$
  $$\text{ApEn}(m) = \phi(m) - \phi(m+1), \qquad \chi^2 = \max(0.0, 2n[\ln 2 - \text{ApEn}(m)])$$
  $$P\text{-value} = Q\left(2^{m-1}, \frac{\chi^2}{2}\right) = \text{gammaincc}\left(2^{m-1}, \frac{\chi^2}{2}\right)$$
  Constraint recommendation per NIST Sec 2.12.7: $m < \lfloor \log_2 n \rfloor - 5$. For 256-bit keys ($n=256$), $\lfloor \log_2 256 \rfloor - 5 = 3$, so default $m=2$ strictly satisfies $m < 3$.
- **Significance Level & Acceptance**: $\alpha = 0.01$. A key is accepted if and only if all three tests are applicable and pass ($P\text{-value} \ge \alpha$).

8. **Key Generation Rate (KGR) Measurement**: Governed by **`PA.pdf`, Section 3.2.8.b, Equation (3.63), page 35**:
```math
\text{KGR} = \frac{N_{\text{bit}}}{T} \qquad (\text{bps}) \qquad (3.63)
```
- **Bit Counting Policy**: Evaluated per path. Alice's final key is counted exactly once ($N_{\text{bit}} = 256$ bits if all three NIST tests pass, $0$ bits if rejected). Bob's matching key is not duplicate-counted. Alice–Bob agreement is reported separately.
- **Timing Policy**: Elapsed software duration $T$ is measured using a monotonic high-resolution timer (`time.perf_counter()`) starting immediately before scalar MSHKF filtering and ending immediately after SHA-256 privacy amplification on that path (PRBS expansion is included only on `prbs_2bit`). Dataset loading, plotting, exports, and NIST testing are strictly excluded.
- **Cache Warm-Up Policy**: A standardized pre-warm step constructs the BCH code and runs a dummy decode prior to timing, eliminating multi-second Numba JIT compilation timing-order bias between paths.

**Methodological Boundary**: Physical channel probing is **postponed, not replaced**. All current calculations use synthetic indoor dummy data strictly for **software validation** (pipeline integrity, parser correctness, mathematical accuracy), not for empirical claims regarding wireless channel reciprocity or eavesdropping resistance. Deterministic LFSR expansion does not add physical channel entropy. Public helper data leaks information up to $(n - k)$ bits per block.

## 2. Dataset & Semantics
- **File Path**: `data/raw/dummy/Dummy RSSI (data Indoor).xlsx`
- **SHA-256**: `50A3459CB0A09D0A2897A2872E18D977EF6ECE0C7FCB68C0549BDB4CD780A0EE`
- **Observations**: 500 rows. Row-wise pairing is strictly confirmed: row index $i$ corresponds to the exact same observation instance across all channels. Row order and sample alignment are strictly preserved throughout filtering, quantization, PRBS, and reconciliation.
- **Column Definitions**:
  - `Alice`: RSSI received by Alice from Bob's signal transmission.
  - `Bob`: RSSI received by Bob from Alice's signal transmission.
  - `Eve1-Alice`: RSSI overheard by eavesdropper Eve from Alice's transmission.
  - `Eve1-Bob`: RSSI overheard by eavesdropper Eve from Bob's transmission.

## 3. Implemented Modules & Validated Results
- **Workbook Loader (`src/rssi_skg/loader.py`)**: Uses `openpyxl` to read raw workbooks; validates presence of all 4 required headers; enforces numeric cell types; reports exact row and column upon encountering missing/invalid values; supports arbitrary sample sizes $N \ge 2$.
- **Modified Sage–Husa Adaptive Kalman Filter (`src/rssi_skg/filter.py`)**:
  - Implements scalar MSHKF with modeling assumptions $\Phi = 1.0$ and $H = 1.0$.
  - Adaptive memory parameter $b = 0.99$ is a selected value within the literature range $(0.95, 0.999)$ mentioned in `PA.pdf` Section 3.2.2. Initial weight $D_0 = 1.0$.
  - Parameters $P_0 = 1.0\ \text{dBm}^2, Q = 0.1\ \text{dBm}^2, R_0 = 1.0\ \text{dBm}^2$ are uncalibrated software-validation assumptions.
  - Process noise covariance $Q = 0.1\ \text{dBm}^2$ is held fixed based on `PA.pdf` Section 3.2.2's final modeling assumption (known prior). Consequently, online adaptation is performed on measurement noise covariance $\hat{R}_k$ while Equation (3.20) for adaptive $Q$ update is not executed.
  - Online adaptation of $\hat{R}_k$ and recursive updates for noise means $\hat{q}_k$ and $\hat{r}_k$ are retained.
  - Sample indexing policy: auto-initialization from first sample $x_0 = z_0$ sets output[0] = $z_0$ and starts recursion at sample $1$ ($k=1$), strictly avoiding double-counting $z_0$.
  - Enforces independent filter instances across Alice, Bob, Eve1-Alice, and Eve1-Bob for strict channel isolation.
- **Correlation Calculation (`src/rssi_skg/correlation.py`)**: Computes centered zero-lag Pearson correlation $\rho$ in `float64` precision; validates equal lengths; rejects $N < 2$, NaN, and Inf; raises explicit `ValueError` on constant sequences (zero variance).
- **Modified Adaptive Dual-Threshold Quantization (`src/rssi_skg/quantization.py`)**:
  - Segment-based adaptive threshold calculation: non-overlapping segments with configurable default window size $W = 50$, multiplier $\alpha = 0.5$, and population standard deviation ($\text{ddof} = 0$).
  - Full sample coverage: processes all samples, including any shorter final segment.
  - Sample retention: all samples are retained; no sample in the intermediate zone is discarded. Constant segments ($\sigma = 0$) unconditionally produce level 1.
  - Channel isolation: each channel's mean, standard deviation, and thresholds are calculated independently with zero cross-channel contamination.
  - Dual binary encodings generated simultaneously in every run:
    - **2-bit Gray code**: $0 \rightarrow 00$, $1 \rightarrow 01$, $2 \rightarrow 11$ (implementation choice to minimize bit errors for adjacent state transitions).
    - **4-bit code**: $0 \rightarrow 1010$, $1 \rightarrow 1011$, $2 \rightarrow 1001$ (per `PA.pdf` Section 3.2.3, page 28).
  - Bitstreams preserve temporal sample order.
  - Evaluation: Bit-level Key Agreement Rate (KAR) per `PA.pdf` Equation (3.64), sample-level agreement rate, and per-channel level frequencies.
  - Companion XLSX Export (`export_quantized_workbook_xlsx`) with Text format (`@`) and >32k cell limit chunking.
  - Visualization (`plot_kar_comparison_figure`): 4-panel 300-dpi PNG and vector PDF.
- **PRBS Expansion Stage (Galois XOR-LFSR, `src/rssi_skg/prbs.py`)**:
  - Left-shift Galois LFSR with primitive polynomials $f(x) = x^2 + x + 1$ ($m=2$) and $f(x) = x^4 + x + 1$ ($m=4$).
  - Produces 1,500 bits/channel (2-bit seed) and 7,500 bits/channel (4-bit seed) across 500 samples.
  - Output recurrence strictly satisfied per `PA.pdf` Equation (3.25) within each sample block.
  - Explicit zero-seed handling: seed `00` locked up at state 0 with actual period 1.
  - Companion multi-sheet XLSX export and 2×2 PRBS KAR comparison figure (`plot_prbs_kar_comparison_figure`).
- **BCH Codeword Helper Data Reconciliation (`src/rssi_skg/reconciliation.py`)**:
  - **Codeword Helper Data Scheme (`PA.pdf` Equations 3.32–3.36)**:
    - Source generates independent random $k$-bit message per block: $M \leftarrow \text{GF}(2)^k$.
    - Encodes $M$ to BCH codeword: $C = \text{BCH\_Encode}(M) \in \text{GF}(2)^n$.
    - Publishes helper data: $H = A \oplus C$.
    - Receiver computes $C' = H \oplus B = C \oplus (A \oplus B) = C \oplus e$.
    - Receiver decodes: $\hat{C} = \text{BCH\_Decode}(C')$. If error weight $w(e) \le t$, $\hat{C} = C$.
    - Receiver reconstructs: $\hat{A} = H \oplus \hat{C}$. If $\hat{C} = C$, then $\hat{A} = A$.
  - **Zero-Padding & Padding Removal**:
    - Final block zero-padded to $n$ bits with explicit tracking of original length $L$ and padding count $P$.
    - Padding stripped immediately after reconstruction: $\hat{A} \leftarrow \hat{A}[:L]$.
    - Excluded from all KAR metrics and payload recovery verification.
  - **Receiver Isolation**:
    - Receiver decoder accesses only its own bits $B$, public helper data $H$, and BCH parameters $(n, k, t)$.
    - Source bitstream $A$ is strictly excluded from decoder operations.
    - Evaluation categories: `success` ($num\_corr \ge 0, \hat{A} == A$), `detected_failure` ($num\_corr == -1$), and `miscorrected` ($num\_corr \ge 0, \hat{A} \ne A$). Source equality verified only in the offline evaluator.
  - **Direct Bitstream Equality & Privacy Amplification Status**:
    - Direct unpadded bitstream equality: $\text{exact\_recovery} = (A == \hat{A}_{\text{unpadded}})$.
    - Privacy Amplification (`PA.pdf` Section 3.2.6) is fully implemented via bit-level SHA-256 compression yielding 256-bit secret keys across both supported reconciled paths.
  - **Four-Path BCH Configuration Architecture (`DEFAULT_BCH_CODE_2BIT = (127, 1, 62)`, `DEFAULT_BCH_CODE_4BIT = (255, 9, 63)`)**:
    - **Experimental Milestone Status**: Reached an **Experimental Reconciliation Milestone with Demonstrated Public-Helper Recovery on Tested Dummy Data**. Downstream stages (Privacy Amplification using bit-level SHA-256, NIST SP 800-22 Rev. 1a statistical testing, and Key Generation Rate) remain intentionally paused.
    - **Baseline & Configuration Error Verification ($N=500$, `dummy`)**:
      * `quant_2bit` ($L=1000$ bits, $n=127, k=1, t=62, d=125$): 8 blocks, 16 pad bits, Alice–Bob errors per block `[17, 18, 16, 34, 16, 14, 37, 44]`, max = **44** ($\le t=62$).
      * `prbs_2bit` ($L=4000$ bits, $n=127, k=1, t=62, d=125$): 32 blocks, 64 pad bits, Alice–Bob errors per block max = **62** ($\le t=62$).
      * `quant_4bit` ($L=2000$ bits, $n=255, k=9, t=63, d=127$): 8 blocks, 40 pad bits, Alice–Bob errors per block `[17, 18, 16, 34, 16, 14, 39, 42]`, max = **42** ($\le t=63$).
      * `prbs_4bit` ($L=4000$ bits, $n=255, k=9, t=63, d=127$): 16 blocks, 80 pad bits, Alice–Bob errors per block `[21, 30, 25, 25, 21, 27, 39, 55, 25, 19, 9, 33, 58, 49, 62, 54]`, max = **62** ($\le t=63$).
      * *Discrepancy Resolution*: Earlier exploratory runs at $n=127$ on 4-bit data produced maxima of 23 for `quant_4bit` and 36 for `prbs_4bit`, which belong strictly to $n=127$ block partitioning. Under the actual $n=255$ configuration, maxima are 42 and 62, both corrected by $t=63$. On 2-bit paths at $n=127$, maxima are 44 and 62, both corrected by $t=62$.
    - **Candidate Search Rationale**:
      * For $n \le 127$, covering error count 36 on `prbs_4bit` forces $k=1$ ($\text{BCH}(127, 1, 62)$). No code with $k > 1$ exists for $n \le 127$.
      * For $n=255$, covering maximum block error 62 with $k > 1$ uniquely selects **$\text{BCH}(255, 9, 63)$** ($d=127, k=9$).
      * Achieves 100% KAR and exact Bob recovery on both `quant_4bit` (8 blocks) and `prbs_4bit` (16 blocks).
    - **Ordinary-Decoder vs. Public-Helper Enumeration Recovery**:
      * *Ordinary Syndrome Decoding*: Legitimate Alice–Bob achieves `exact_recovery = True` (100.00% post-KAR). Passive eavesdropper decoding achieves `exact_recovery = False` across all paths due to detected decoding failures and miscorrections.
      * *Ordinary Post-KAR Bit Agreement*: Eve's ordinary decoding failure does **NOT** mean 0% recovered bits; Eve retains 61.90%–74.60% bit agreement on 2-bit paths, and 81.85%–96.35% bit agreement on 4-bit paths.
      * *Bounded Public-Helper Candidate Analysis ($k=9, 512$ Codewords)*:
        1. Eavesdropper pre-enumerates all 512 codewords $C \in \mathcal{C}$ in $< 0.1$ s and forms $A_{\text{cand}} = H \oplus C$.
        2. Complete public alphabet: Quantizer outputs are publicly fixed to 3 symbols by PA.pdf Eq (3.23) and `CODE_4BIT_MAP` (`{"1010", "1011", "1001"}`). Expanding these 3 seeds through the 8-clock Galois LFSR yields exactly 3 valid 8-bit PRBS codewords (`{"10111100", "10101111", "10001001"}`). Neither is a private subset learned from Alice.
        3. Generator matrix rank: Candidate equations $m \cdot G_{*, J} = (h \oplus v)_J$ constrain the code space. We proved that $\text{rank}(G_{*, J}) = 9$ over $\text{GF}(2)$ on both the 40 trailing zero-padding columns and the sample bit columns, spanning the full 9 message dimensions.
        4. Symbol boundary filtering: Pruning candidates across complete symbol boundaries reduces the candidate set from 512 to **exactly 1 candidate per block** across all 8 blocks of `quant_4bit` and all 16 blocks of `prbs_4bit`.
        5. Ground-truth evaluation: Evaluated strictly *after* candidate selection, the unique candidate matches Alice's true bitstream with **100% accuracy and 0 unresolved ambiguity**.
    - **Cryptographic Secrecy Finding & Impossibility of Restoration via Hashing**:
      * Ordinary syndrome decoder failure and small $k$ ($k=9$) do NOT establish cryptographic secrecy; $n - k = 246$ independent linear parity constraints exist on the public channel.
      * Because Eve uniquely reconstructs Alice's entire unpadded bitstream $A$ from public data alone, **hashing a fully recovered input cannot restore secrecy**.
      * Whether privacy amplification employs the repository's historical bit-level SHA-256 implementation (PA.pdf Section 3.2.6, Equations 3.37–3.53) or universal hashing with a publicly broadcast seed, evaluating any deterministic public hash function on a known input $A$ produces a digest $K = \text{Hash}(A)$ that Eve computes identically.
  - **Shared BCH Parameter Investigation & Public Information Leakage Audit**:
    - Evaluated primitive lengths $n \in \{31, 63, 127, 255, 511, 1023\}$ across both supported paths (`quant_2bit` and `prbs_2bit`) on the actual dummy dataset:
      * Without interleaving:
        - $n=31$: max error = 21 (max valid $t$ for $k>1$ is 7 $\implies$ FAIL).
        - $n=63$: max error = 32 (max valid $t$ for $k>1$ is 15 $\implies$ FAIL).
        - $n=127$: max error = 49 (max valid $t$ for $k>1$ is 31 $\implies$ FAIL).
        - $n=255$: max error = 90 (max valid $t$ for $k>1$ is 60 $\implies$ FAIL).
        - $n=511$: max error = 164 (max valid $t$ for $k>1$ is 126 $\implies$ FAIL).
        - $n=1023$: `quant_2bit` max error = 196, `prbs_2bit` max error = 192 (global max = 196). Valid candidate: $\text{BCH}(1023, 46, d_{\text{designed}}=401, t=200)$.
      * With deterministic public interleaving (seed 2026):
        - $n=31$: max error = 12 (max $t=7 \implies$ FAIL).
        - $n=63$: max error = 21 (max $t=15 \implies$ FAIL).
        - $n=127$: max error = 36 (max $t=31 \implies$ FAIL).
        - $n=255$: max error = 67 (max $t=60 \implies$ FAIL).
        - $n=511$: max error = 127 (max $t=126 \implies$ FAIL by 1 bit).
        - $n=1023$: `quant_2bit` max error = 196, `prbs_2bit` max error = 179 (global max = 196). Valid candidate: $\text{BCH}(1023, 46, t=200)$.
    - **Public Information Leakage Audit (Padding & Linear Constraints)**:
      * For $\text{BCH}(1023, 46, t=200)$ on `prbs_2bit` ($L=1500, M=2$ blocks, $N_{pad}=546$ zero-padding bits):
        - With Interleaving (seed 2026): Padding is dispersed (Block 0 has 276 padding bits, Block 1 has 270 padding bits).
          The exact $\text{GF}(2)$ rank of the submatrix formed by public padding columns $G[:, J]$ is **46 out of 46 (full rank)** in both blocks!
          Because $h_J = u G[:, J] \oplus A_J$ and $A_J = 0$, $u$ is determined via direct matrix inversion over $\text{GF}(2)$, completely recovering Alice's message, codeword, and source bitstream ($K_E = K_A$, key leaked).
        - Without Interleaving: Block 1 has 546 padding bits, also yielding $\text{rank}_{\text{GF}(2)}(G[:, J]) = 46$ (full rank, completely leaked).
    - **Integration Decision**:
      * Because the shared candidate $\text{BCH}(1023, 46, t=200)$ fails the secrecy/leakage criterion, it is not adopted as production default.
      * In accordance with the decision rule, **calibrated 2-bit defaults are preserved**:
        - `quant_2bit`: $\text{BCH}(31, 1, 15)$
        - `prbs_2bit`: $\text{BCH}(127, 1, 63)$
  - **Historical Calibrated Diagnostic Exploration ($N=500$ samples, `data_kind=dummy`, Superseded Model)**:
    *(Notice: This diagnostic exploration used an earlier model with separate Bob-generated helper data for Bob–Eve1-Bob. That model is superseded by the single-session Alice reference model).*
    - `quant_2bit` (1,000b): Diagnostic BCH(31, 1, 15), 33 blocks, max block error = 14 $\le 15$.
      * Alice–Bob: Pre-KAR 80.40% $\to$ Post-KAR 100.00%, Exact=True, 33/33 success, helper overhead 1.02x (1023b).
      * Alice–Eve1-Alice: Pre-KAR 58.20% $\to$ Post-KAR 75.20%, 25/33 success, 8 miscorrected, Exact=False.
      * Bob–Eve1-Bob (Superseded): Pre-KAR 55.40% $\to$ Post-KAR 69.00%, 23/33 success, 10 miscorrected, Exact=False.
    - `prbs_2bit` (1,500b): Diagnostic BCH(127, 1, 63), 12 blocks, max block error = 49 $\le 63$.
      * Alice–Bob: Pre-KAR 76.27% $\to$ Post-KAR 100.00%, Exact=True, 12/12 success, helper overhead 1.02x (1524b).
      * Alice–Eve1-Alice: Pre-KAR 56.53% $\to$ Post-KAR 66.13%, 8/12 success, 4 miscorrected, Exact=False.
      * Bob–Eve1-Bob (Superseded): Pre-KAR 56.27% $\to$ Post-KAR 74.60%, 9/12 success, 3 miscorrected, Exact=False.
  - **Generated Output Artifacts in `outputs/`**:
    - `dummy_rssi_reconcile_metrics.csv` (6 rows: 2 paths $\times$ 3 pairs)
    - `dummy_rssi_reconcile_blocks.csv`
    - `dummy_rssi_reconcile_config.json`
    - `dummy_rssi_bch_metrics.csv`
    - `dummy_rssi_bch_blocks.csv`
    - `dummy_rssi_bch_config.json`
    - `dummy_rssi_bch.xlsx` (companion multi-sheet Excel workbook with Text `@` formatting and >32k cell chunking)
    - `dummy_rssi_bch_reconciliation.png` & `.pdf` (2×2 300-dpi / vector PDF reconciliation figure)
  - **PRBS 8-Clock Expansion & Four-Path BCH Selection**:
    - Generates exactly **8 PRBS output bits per sample** for both 2-bit and 4-bit quantization paths by executing 8 Galois LFSR clocks.
    - Preserves register degree ($m=2$ and $m=4$), maximal periods ($2^2-1=3$ and $2^4-1=15$), polynomial taps, shift direction, and zero-seed lockup to `'00000000'` (actual period 1).
    - For $N=500$ retained dummy samples, verified stream lengths:
      * `quant_2bit`: 1,000 bits ($2N$)
      * `quant_4bit`: 2,000 bits ($4N$)
      * `prbs_2bit`: 4,000 bits ($8N$)
      * `prbs_4bit`: 4,000 bits ($8N$)
    - **Shared BCH Parameter Selection across All 4 Paths**:
      * Evaluated candidate Galois block lengths $n \in \{31, 63, 127, 255, 511, 1023\}$.
      * Codes with $n \le 63$ cannot correct `prbs_2bit` errors (worst-block errors exceed $(n-1)/2$).
      * For $n=127$, worst-block errors are: `quant_2bit` = 44, `quant_4bit` = 23, `prbs_2bit` = 62, `prbs_4bit` = 36.
      * Selected shared code: **$\text{BCH}(127, 1, 62)$ with designed distance $d=125$**.
      * Achieves 100% exact bitstream recovery (`Alice–Bob`) across all four paths:
        - `quant_2bit`: 8 blocks, 16 pad bits, max block errors = 44 $\le 62$, Exact match: TRUE.
        - `quant_4bit`: 16 blocks, 32 pad bits, max block errors = 23 $\le 62$, Exact match: TRUE.
        - `prbs_2bit`: 32 blocks, 64 pad bits, max block errors = 62 $\le 62$, Exact match: TRUE.
        - `prbs_4bit`: 32 blocks, 64 pad bits, max block errors = 36 $\le 62$, Exact match: TRUE.
    - **Tradeoff & Information Leakage**:
      * Shared code rate is $k/n = 1/127 \approx 0.00787$.
      * Leaks $n - k = 126$ parity bits per block (99.2% parity leakage).
      * Because $t=62$ is oversized for 4-bit paths (<18% BER), passive eavesdroppers also decode `quant_4bit` and `prbs_4bit` completely.
      * Per-path alternative codes (e.g. $\text{BCH}(127, 43, 14)$ for `quant_4bit` and $\text{BCH}(127, 29, 21)$ for `prbs_4bit`) are documented as scientific alternatives to restore code rate and prevent Eve decoding.
    - **Paused Downstream Evaluation**:
      * Downstream pipeline execution (Privacy Amplification, NIST statistical randomness testing, and Key Generation Rate) is explicitly paused for the 8-bit PRBS / 4-path revision pending 4-path key derivation architecture. Historical PA/NIST/KGR benchmarks reflect the previous 2-bit baseline.
- **Privacy Amplification Stage (Bit-Level SHA-256, `src/rssi_skg/privacy_amplification.py`)**:
  - Implements bit-level SHA-256 Privacy Amplification strictly following **`PA.pdf` Section 3.2.6 (Equations 3.37–3.53, FIPS PUB 180-4)**.
  - **Bit-Level Padding (`pad_bitstream`)**:
    - Operates directly on unpadded bitstreams $M$ of arbitrary bit length $L$:
      $$M' = M \parallel 1 \parallel 0^p \parallel [L]_{64}$$
      where $L + 1 + p \equiv 448 \pmod{512}$, $0 \le p < 512$, and $[L]_{64}$ is the 64-bit big-endian binary representation of the unpadded bit length $L$.
    - `quant_2bit` ($L = 1000$ bits) $\to 1000 + 1 + 471 + 64 = 1536 = 3 \times 512$ bits (3 blocks, $p=471$).
    - `prbs_2bit` ($L = 1500$ bits) $\to 1500 + 1 + 483 + 64 = 2048 = 4 \times 512$ bits (4 blocks, $p=483$).
  - **64-Round Compression & Message Scheduling (`sha256_bitstream`)**:
    - Computes message schedule $W_0, \dots, W_{63}$ per Equations (3.46)–(3.47) and round compression updates $a, b, c, d, e, f, g, h$ per Equations (3.48)–(3.53) initialized with fractional square root constants of the first 8 primes $H^{(0)}$ and 64 round constants from fractional cube roots $K_t$.
    - Yields a 256-bit secret key $K = (K_{\text{bin}}, K_{\text{hex}})$ (256-character binary string and 64-character lowercase hex digest).
    - Validated against NIST standard test vectors, independently-sourced bit-oriented Known Answer Tests (CAVP `SHA256ShortMsg.rsp`), and byte-aligned parity checks with Python `hashlib.sha256`.
  - **Channel Isolation & Pair Evaluation**:
    - Processes all 4 physical channels independently: `Alice`, `Bob`, `Eve1-Alice`, and `Eve1-Bob`.
    - Under the authoritative eavesdropper threat model, there is strictly ONE legitimate Alice–Bob session with Alice as reference. Alice's public helper data is generated once per path and reused for Bob and both Eve observation streams (`Eve1-Alice` and `Eve1-Bob`).
    - Evaluates 3 pairs: the legitimate pair (`Alice–Bob`) and the two separate passive eavesdropping streams evaluated against Alice's reference key (`Alice–Eve1-Alice` and `Alice–Eve1-Bob`) across both supported reconciled 2-bit paths (`quant_2bit` and `prbs_2bit`).
    - Reports:
      * `pre_pa_kar`: Bit-level Key Agreement Rate from unpadded reconciled bitstreams before SHA-256.
      * `post_pa_kar`: Bit-level Key Agreement Rate between 256-bit final keys per `PA.pdf` Equation (3.64):
        $$\text{KAR}_{\text{post}} = \frac{256 - d_H(K_{\text{src}}, K_{\text{rcv}})}{256} \times 100\%$$
      * `exact_key_match`: Boolean flag ($K_{\text{source}} == K_{\text{receiver}}$).
    *(Note: Evaluated strictly per PA.pdf; standalone Hamming distance report column is omitted from exported CSV/XLSX summaries and preserved internally on dataclasses for KAR computation).*
  - **Scientific Secrecy Boundary**:
    - Standard scientific notice: Generating a 256-bit key via SHA-256 hashes down the bitstream cryptographically, but does **NOT** imply 256 bits of true physical min-entropy when upstream PRBS bit expansion is deterministic and public BCH helper data leaks linear parity relations.
    - An attacker who recovers the source bits algebraically from public helper data computes the identical SHA-256 digest; ~50% Post-PA KAR under ordinary decoding failure does not establish cryptographic secrecy.
  - **Companion Artifacts & Visualization**:
    - CSV outputs: `dummy_rssi_pa_metrics.csv` (Pre vs Post KAR across paths and pairs), `dummy_rssi_pa_keys.csv` (role, path, 256-bit binary key string, 64-char hex digest).
    - JSON config: `dummy_rssi_pa_config.json`.
    - Companion XLSX: `dummy_rssi_pa.xlsx` using `openpyxl` with explicit `@` (Text) format for all key cells to preserve leading zeros.
    - 2×2 Visualization: `dummy_rssi_pa_comparison.png` (300-dpi raster) and `dummy_rssi_pa_comparison.pdf` (vector) generated by `plot_privacy_amplification_figure`.

  - **NIST SP 800-22 Randomness Testing (`src/rssi_skg/nist.py`)**:
    - Implements three core statistical tests per `PA.pdf` Section 3.2.8.d and NIST SP 800-22 Rev. 1a:
      1. Frequency (Monobit) Test (Equations 3.65–3.66, NIST Sec 2.1).
      2. Runs Test (Equations 3.67–3.69, NIST Sec 2.3) with explicit prerequisite check $|\pi - 0.5| < 2/\sqrt{n}$. Prerequisite failure explicitly yields $P\text{-value} = 0.0$, `applicable=False`, and documented reason.
      3. Approximate Entropy Test (Equations 3.70–3.73, NIST Sec 2.12) with default $m=2$ and constraint $m < \lfloor \log_2 n \rfloor - 5$.
    - Significance level $\alpha = 0.01$. Overall acceptance requires all three tests to be applicable and passed.
    - Reference test vectors from NIST SP 800-22 Rev. 1a Sections 2.1.8, 2.3.8, and 2.12.8 verified with exact numerical match to 6 decimal places.
    - Exporters: `export_nist_metrics_csv` (wide format per key) and `export_nist_config_json`.

  - **Key Generation Rate (KGR) Measurement (`src/rssi_skg/kgr.py`)**:
    - Implements KGR per `PA.pdf` Section 3.2.8.b, Equation (3.63): $\text{KGR} = N_{\text{bit}} / T$ (bps).
    - Bit counting policy: Alice's 256-bit key is counted once ($N_{\text{bit}} = 256$ if accepted, $0$ if rejected). Bob's key is not duplicate-counted. Alice–Bob exact key agreement is reported separately.
    - High-resolution timing: Independent per-path measurement using monotonic timer `time.perf_counter()` spanning immediately before MSHKF filtering through SHA-256 compression (PRBS expansion included on `prbs_2bit` only). Excludes workbook loading, plotting, exports, and NIST testing.
    - Cold-start & cache policy: `warm_up_bch_cache()` pre-compiles Galois Numba JIT kernels and tables before timing, eliminating ~5.3 s initial compilation order bias between paths.
    - Exporters: `export_kgr_metrics_csv`, `export_kgr_config_json`, and companion multi-sheet Excel workbook `export_evaluation_workbook_xlsx` with `@` (Text) format for key cells.

## 4. Key Source & Test File Responsibilities
- `src/rssi_skg/nist.py`: NIST SP 800-22 statistical test suite (`monobit_test`, `runs_test`, `approximate_entropy_test`), key validator (`evaluate_key_randomness`, `evaluate_pa_keys_randomness`), and artifact exporters (`export_nist_metrics_csv`, `export_nist_config_json`).
- `src/rssi_skg/kgr.py`: High-resolution software KGR measurement (`measure_multipath_kgr`, `execute_timed_path_pipeline`), cache pre-warming (`warm_up_bch_cache`), injectable mock clock support, and companion Excel exporter (`export_evaluation_workbook_xlsx`).
- `src/rssi_skg/privacy_amplification.py`: Bit-level SHA-256 Privacy Amplification engine per FIPS 180-4 (`PA.pdf` Section 3.2.6), bit-level padding (`pad_bitstream`), 64-round compression (`sha256_bitstream`), `PrivacyAmplificationConfig`, `ChannelPrivacyAmplificationResult`, `PairPrivacyAmplificationResult`, `MultiPathPrivacyAmplificationResult`, `amplify_privacy_all_paths`, artifact exporters (`export_pa_metrics_csv`, `export_pa_keys_csv`, `export_pa_config_json`, `export_pa_workbook_xlsx`), and `verify_against_hashlib`.
- `src/rssi_skg/reconciliation.py`: Codeword helper data engine, BCH code caching (`get_bch_code`), `ReconciliationConfig`, `serialize_bitstream`, `generate_candidate_key`, `generate_helper_data`, `reconstruct_receiver_bitstream`, `evaluate_reconciliation_pair`, `reconcile_all_paths`, artifact CSV/JSON exporters, and `export_reconciliation_workbook_xlsx`.
- `src/rssi_skg/prbs.py`: Galois XOR-LFSR engine (`GaloisLFSR`), primitive polynomial definitions, `PRBSConfig`, `expand_seed`, `expand_channel_prbs`, `expand_channels_prbs`, artifact CSV/JSON exporters, and `export_prbs_workbook_xlsx`.
- `src/rssi_skg/quantization.py`: Modified ADQ engine, `QuantizationConfig`, `SegmentThresholds`, `ChannelQuantizationResult`, `quantize_series`, `quantize_channels`, `encode_levels_to_bits`, `calculate_kar`, `calculate_level_agreement`, `calculate_level_frequencies`, CSV/JSON export functions, and `export_quantized_workbook_xlsx`.
- `src/rssi_skg/filter.py`: Scalar MSHKF engine, `FilterConfig`, `ModifiedSageHusaFilter`, `filter_rssi_channels`.
- `src/rssi_skg/correlation.py`: Pure mathematical Pearson implementation and input sanity checking.
- `src/rssi_skg/loader.py`: Excel workbook ingestion, column validation, and row pairing.
- `src/rssi_skg/plotting.py`: Bubble aggregation, raw figure rendering, filtered comparison figure, quantization KAR figure (`plot_kar_comparison_figure`), 2×2 PRBS KAR figure (`plot_prbs_kar_comparison_figure`), 2-panel reconciliation figure (`plot_reconciliation_figure`), and 2×2 Privacy Amplification comparison figure (`plot_privacy_amplification_figure`).
- `src/rssi_skg/cli.py`: Unified CLI parsing with prerequisite chaining, `--nist` and `--kgr` evaluation options, companion XLSX export dispatch, figure prefix routing, and stdout user guidance.
- `tests/test_nist.py`: 12 tests (Monobit official NIST reference vector, Monobit edge cases, Runs official NIST reference vector, Runs prerequisite failure handling, Runs edge cases, ApEn official NIST reference vector, ApEn constraint enforcement, input validation, short length rejection, overall acceptance logic, full pipeline evaluation on dummy data, and CSV/JSON exporters).
- `tests/test_kgr.py`: 7 tests (controlled mock clock injection, single Alice accounting / Bob non-duplication, statistical rejection gating to 0 bps, cache warm-up execution, realistic dummy data measurement, CSV/JSON/multi-sheet XLSX companion exporters, and full CLI integration).
- `tests/test_privacy_amplification.py`: 12 tests (FIPS 180-4 bit padding correctness, SHA-256 compression against NIST vectors including bit-oriented Known Answer Tests with proven provenance, padding boundary transitions at 447/448 and 511/512 bits with byte-aligned `hashlib.sha256` cross-verification, non-byte-aligned arbitrary bit lengths $L=1000$ and $L=1500$, avalanche diffusion sanity checks, independent channel isolation, end-to-end 2-path evaluation on dummy dataset, CSV/JSON/XLSX exporters, `@` Text formatting verification, CLI execution, candidate key flag aliases).
- `tests/test_reconciliation.py`: 15 tests (BCH code cache & properties validation, privacy amplification removal verification, error-free recovery, controlled error-correction up to t, beyond-t error handling, zero-padding addition & stripping, receiver/Eve channel isolation, 2-path reconciliation with obsolete option rejection, identical path parameter verification, second small valid BCH configuration test, dynamic CSV/JSON/XLSX companion exporters, CLI full pipeline, obsolete CLI options rejection, global BCH code properties & metadata, global BCH 2-path recovery & 2x2 figure export).
- `tests/test_prbs.py`: 15 tests (primitive polynomials, zero-state lockup, known-answer sequences, Equation 3.25 recurrence, boundary resets, input validation, channel isolation, exports, cell chunking, CLI).
- `tests/test_quantization.py`: 16 tests (threshold calculation, boundary conditions, both encodings, sample sequence preservation, constant segments, partial segments, channel isolation, KAR formula, level agreement, invalid configs, invalid inputs, dummy dataset, CLI export, XLSX companion, cell limit chunking, plotting).
- `tests/test_filter.py`: 11 tests (intermediate step validation against independent 2-step example, channel isolation, sample indexing, constant-input behavior, numerical safeguards, invalid configs, non-finite inputs, dummy dataset, CLI integration).
- `tests/test_correlation.py`: 8 tests (perfect positive/negative, zero correlation, zero variance, invalid dimensions, NaN/Inf, SciPy reference parity).
- `tests/test_loader.py`: 6 tests (missing columns, non-numeric values, empty cells, row ordering preservation, arbitrary $N$).
- `tests/test_plotting.py`: 11 tests (duplicate point aggregation math, dimension checks, figure generation, headless export, CSV-only execution, comparison figure generation, PRBS KAR records input, PRBS KAR CSV input with self-contained tmp_path fixture, PRBS input validation, CLI PRBS figure export, CLI PRBS auto-derivation).

## 5. Verification Records
- **Clean Environment**: Project installed in isolated local `.venv` via `pip install -e ".[dev]"`.
- **Test Suite & Independence**: 119 automated tests pass (`pytest -v` exited 0 with 119/119 passing across 10 test modules).
  - *Threat Model Verification*: Added regression tests `test_eavesdropper_threat_model_helper_data_reuse_and_isolation` and `test_eavesdropper_threat_model_pa_keys_and_reference_comparison` proving Alice helper data reuse, passive receiver isolation, common Alice reference comparison, and absence of extraneous Bob-source keys.
  - *Test Independence Audit*: Identified that `test_plot_prbs_kar_comparison_figure_from_csv` previously relied on pre-existing `outputs/dummy_rssi_prbs_metrics.csv`. Fixed by generating isolated synthetic CSV data within pytest's `tmp_path`. Verified by executing the full test suite with `outputs/` completely unavailable (`outputs_backup`); all tests passed cleanly with zero cross-test or disk dependencies.
  - *Decoding Rigor*: Distinction between detected failures and miscorrections is mathematically enforced. The decoder operates solely on syndromes and does not have access to the true channel error count; channel errors exceeding $t$ produce either detected failure or miscorrection.
- **CLI Execution**: Executed raw-only, filtering-only, quantization, PRBS, global BCH reconciliation, bit-level SHA-256 Privacy Amplification, NIST SP 800-22 randomness testing, and KGR measurement pipelines against the dummy workbook.

### Two-Path NIST SP 800-22 Randomness Results (Alpha=0.01, ApEn m=2, n=256 bits)
- **Path `quant_2bit`**:
  - `Alice`: Monobit $s_{\text{obs}}=1.1250$ ($p=0.2606$ PASS), Runs $V_n=122$ ($p=0.5002$ PASS), ApEn $\chi^2=2.1328$ ($p=0.7122$ PASS) $\implies$ **ACCEPTED**.
  - `Bob`: Monobit $s_{\text{obs}}=1.1250$ ($p=0.2606$ PASS), Runs $V_n=122$ ($p=0.5002$ PASS), ApEn $\chi^2=2.1328$ ($p=0.7122$ PASS) $\implies$ **ACCEPTED**.
  - `Eve1-Alice`: Monobit $s_{\text{obs}}=2.0000$ ($p=0.0455$ PASS), Runs $V_n=125$ ($p=0.8990$ PASS), ApEn $\chi^2=6.7058$ ($p=0.1523$ PASS) $\implies$ **ACCEPTED**.
  - `Eve1-Bob`: Monobit $s_{\text{obs}}=1.1250$ ($p=0.2606$ PASS), Runs $V_n=125$ ($p=0.7662$ PASS), ApEn $\chi^2=2.1245$ ($p=0.7132$ PASS) $\implies$ **ACCEPTED**.
- **Path `prbs_2bit`**:
  - `Alice`: Monobit $s_{\text{obs}}=0.2500$ ($p=0.8026$ PASS), Runs $V_n=123$ ($p=0.5344$ PASS), ApEn $\chi^2=2.5539$ ($p=0.6356$ PASS) $\implies$ **ACCEPTED**.
  - `Bob`: Monobit $s_{\text{obs}}=0.2500$ ($p=0.8026$ PASS), Runs $V_n=123$ ($p=0.5344$ PASS), ApEn $\chi^2=2.5539$ ($p=0.6356$ PASS) $\implies$ **ACCEPTED**.
  - `Eve1-Alice`: Monobit $s_{\text{obs}}=0.7500$ ($p=0.4533$ PASS), Runs $V_n=127$ ($p=0.9283$ PASS), ApEn $\chi^2=0.6775$ ($p=0.9533$ PASS) $\implies$ **ACCEPTED**.
  - `Eve1-Bob`: Monobit $s_{\text{obs}}=0.5000$ ($p=0.6171$ PASS), Runs $V_n=125$ ($p=0.7191$ PASS), ApEn $\chi^2=2.0837$ ($p=0.7212$ PASS) $\implies$ **ACCEPTED**.

### Two-Path Key Generation Rate (KGR) Results (PA.pdf Eq 3.63, Warm BCH Cache)
- **Timer Scope**: Immediate entry to `filter_rssi_channels` $\to$ completion of `sha256_bitstream` across legitimate Alice–Bob channel pipeline.
- **Cache Warm-Up**: `warm_up_bch_cache(DEFAULT_BCH_CODE)` pre-executed before starting timer.
- **Path `quant_2bit`**:
  - Raw Generated Bits ($N_{\text{raw}}$): 256 bits
  - NIST Passed: YES (all 3 tests pass)
  - Accepted Bits ($N_{\text{bit}}$): 256 bits
  - Elapsed Time ($T$): 34.83 ms (0.034830 s)
  - Accepted KGR: **7,349.90 bps**
  - Raw KGR: 7,349.90 bps
  - Alice–Bob Exact Match: TRUE (100.00% KAR)
- **Path `prbs_2bit`**:
  - Raw Generated Bits ($N_{\text{raw}}$): 256 bits
  - NIST Passed: YES (all 3 tests pass)
  - Accepted Bits ($N_{\text{bit}}$): 256 bits
  - Elapsed Time ($T$): 84.19 ms (0.084186 s)
  - Accepted KGR: **3,040.90 bps**
  - Raw KGR: 3,040.90 bps
  - Alice–Bob Exact Match: TRUE (100.00% KAR)

### Four-Path BCH Reconciliation Results (2-bit: BCH(127,1,62), 4-bit: BCH(255,9,63), Interleaving OFF)
- **Parameters**:
  - 2-bit paths (`quant_2bit`, `prbs_2bit`): $n = 127, k = 1, t = 62, d = 125$.
  - 4-bit paths (`quant_4bit`, `prbs_4bit`): $n = 255, k = 9, t = 63, d = 127$.
  - Interleaving `OFF` across all paths. Single Alice reference; helper data reused for Bob and both Eve observation streams.
- **`quant_2bit` (8 blocks, 16 pad bits excluded, BCH(127,1,62))**:
  - Alice–Bob: Pre-KAR 80.40% $\to$ Post-KAR **100.00%** ($\Delta = +19.60\text{ pp}$), Exact: **TRUE**, Blocks (S/F/M): 8/0/0.
  - Alice–Eve1-Alice (Stream 1): Pre-KAR 58.20% $\to$ Post-KAR 61.90% ($\Delta = +3.70\text{ pp}$), Exact: **FALSE**, Blocks (S/F/M): 5/0/3.
  - Alice–Eve1-Bob (Stream 2): Pre-KAR 57.80% $\to$ Post-KAR 74.60% ($\Delta = +16.80\text{ pp}$), Exact: **FALSE**, Blocks (S/F/M): 6/0/2.
- **`quant_4bit` (8 blocks, 40 pad bits excluded, BCH(255,9,63))**:
  - Alice–Bob: Pre-KAR 90.20% $\to$ Post-KAR **100.00%** ($\Delta = +9.80\text{ pp}$), Exact: **TRUE**, Blocks (S/F/M): 8/0/0.
  - Alice–Eve1-Alice (Stream 1): Pre-KAR 79.10% $\to$ Post-KAR 89.60% ($\Delta = +10.50\text{ pp}$), Exact: **FALSE**, Blocks (S/F/M): 5/3/0.
  - Alice–Eve1-Bob (Stream 2): Pre-KAR 78.90% $\to$ Post-KAR 96.35% ($\Delta = +17.45\text{ pp}$), Exact: **FALSE**, Blocks (S/F/M): 7/1/0.
- **`prbs_2bit` (32 blocks, 64 pad bits excluded, BCH(127,1,62))**:
  - Alice–Bob: Pre-KAR 75.85% $\to$ Post-KAR **100.00%** ($\Delta = +24.15\text{ pp}$), Exact: **TRUE**, Blocks (S/F/M): 32/0/0.
  - Alice–Eve1-Alice (Stream 1): Pre-KAR 56.10% $\to$ Post-KAR 63.48% ($\Delta = +7.38\text{ pp}$), Exact: **FALSE**, Blocks (S/F/M): 20/1/11.
  - Alice–Eve1-Bob (Stream 2): Pre-KAR 55.67% $\to$ Post-KAR 66.65% ($\Delta = +10.98\text{ pp}$), Exact: **FALSE**, Blocks (S/F/M): 21/1/10.
- **`prbs_4bit` (16 blocks, 80 pad bits excluded, BCH(255,9,63))**:
  - Alice–Bob: Pre-KAR 86.20% $\to$ Post-KAR **100.00%** ($\Delta = +13.80\text{ pp}$), Exact: **TRUE**, Blocks (S/F/M): 16/0/0.
  - Alice–Eve1-Alice (Stream 1): Pre-KAR 73.25% $\to$ Post-KAR 81.85% ($\Delta = +8.60\text{ pp}$), Exact: **FALSE**, Blocks (S/F/M): 7/9/0.
  - Alice–Eve1-Bob (Stream 2): Pre-KAR 72.90% $\to$ Post-KAR 82.05% ($\Delta = +9.15\text{ pp}$), Exact: **FALSE**, Blocks (S/F/M): 7/9/0.

### Two-Path Privacy Amplification Results (SHA-256 Bit-Level Compression, FIPS 180-4)
- **Mathematical Specification**: Bit-level SHA-256 Privacy Amplification (`PA.pdf` Section 3.2.6, Equations 3.37–3.53). Padding $M' = M \parallel 1 \parallel 0^p \parallel [L]_{64}$, yielding 256-bit secret key $K$.
- **Path: `quant_2bit` ($L = 1000$ bits $\to 256$ bits)**:
  - Alice–Bob: Pre-PA KAR 100.00% $\to$ Post-PA KAR **100.00%** ($\Delta = 0.00\text{ pp}$), Exact Key Match: **TRUE (MATCH)**.
    - Key Hex (both Alice and Bob Reconciled Receiver): `98cadafbd85954df27fd02d37199f75e57e9efb0118b247f02db2b81030fd764`
  - Alice–Eve1-Alice: Pre-PA KAR 58.20% $\to$ Post-PA KAR **50.39%** ($\Delta = -7.81\text{ pp}$), Exact Key Match: **FALSE (MISMATCH)** (127/256 mismatches).
    - Key Hex (Eve1-Alice): `bb8de661d797ee9f0cb06c3dbf58a6a50607799b67ec3fd596cfa9ad591e247d`
  - Alice–Eve1-Bob: Pre-PA KAR 57.80% $\to$ Post-PA KAR **42.19%** ($\Delta = -15.61\text{ pp}$), Exact Key Match: **FALSE (MISMATCH)** (148/256 mismatches).
    - Key Hex (Eve1-Bob): `e5a5c17476411af6221438058bcf28f931b5914dfaf99bd016801035696e4719`
- **Path: `prbs_2bit` ($L = 1500$ bits $\to 256$ bits)**:
  - Alice–Bob: Pre-PA KAR 100.00% $\to$ Post-PA KAR **100.00%** ($\Delta = 0.00\text{ pp}$), Exact Key Match: **TRUE (MATCH)**.
    - Key Hex (both Alice and Bob Reconciled Receiver): `39c81f5d669fddce09059213589b68fa81f79f3ac9302a361301bbc9e50c94e6`
  - Alice–Eve1-Alice: Pre-PA KAR 68.93% $\to$ Post-PA KAR **50.78%** ($\Delta = -18.15\text{ pp}$), Exact Key Match: **FALSE (MISMATCH)** (126/256 mismatches).
    - Key Hex (Eve1-Alice): `ef36998806f42bdfec287859320892e58dc1735e8a78a8fd89a0ec094db4a123`
  - Alice–Eve1-Bob: Pre-PA KAR 55.87% $\to$ Post-PA KAR **47.66%** ($\Delta = -8.21\text{ pp}$), Exact Key Match: **FALSE (MISMATCH)** (134/256 mismatches).
    - Key Hex (Eve1-Bob): `075ee9dee6716684cd81a77840513cfebc926858717d0d8bac3c568b506d6320`

## 6. Windows PowerShell Reproduction Commands
> The primary execution guide with output locations is maintained in [README.md](../README.md#petunjuk-penyiapan-lingkungan--eksekusi).

```powershell
# 1. Run automated test suite (119 tests)
.\.venv\Scripts\python.exe -m pytest -v

# 2. Run default correlation analysis (raw only)
.\.venv\Scripts\python.exe -m rssi_skg -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" -o "outputs/dummy_rssi_correlation.csv" --figure-prefix "outputs/dummy_rssi_correlation"

# 3. Run filtering and correlation pipeline (MSHKF + Raw vs Filtered export)
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --filtered-samples-output "outputs/dummy_rssi_filtered_samples.csv" `
  --filter-config-output "outputs/dummy_rssi_filter_config.json" `
  --figure-prefix "outputs/dummy_rssi_filtered"

# 4. Run full pipeline with Modified ADQ Quantization stage, companion XLSX, and KAR comparison charts
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

# 5. Run full pipeline with PRBS bit expansion stage, companion multi-sheet XLSX, and 2x2 PRBS KAR visualization
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

# 6. Run full pipeline through global BCH reconciliation and candidate key generation
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --quantize `
  --prbs `
  --reconcile `
  --reconcile-metrics-output "outputs/dummy_rssi_reconcile_metrics.csv" `
  --reconcile-blocks-output "outputs/dummy_rssi_reconcile_blocks.csv" `
  --reconcile-config-output "outputs/dummy_rssi_reconcile_config.json" `
  --reconcile-keys-output "outputs/dummy_rssi_reconcile_keys.json" `
  --reconciled-xlsx-output "outputs/dummy_rssi_reconciled.xlsx" `
  --reconcile-figure-prefix "outputs/dummy_rssi_reconciliation"

# 7. Run full pipeline through Privacy Amplification (SHA-256 256-bit key generation)
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

# 8. Run full pipeline through NIST SP 800-22 randomness testing & Key Generation Rate (KGR) measurement
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
  --filter `
  --quantize `
  --prbs `
  --reconcile `
  --pa `
  --nist `
  --kgr `
  --nist-metrics-output "outputs/nist_metrics.csv" `
  --nist-config-output "outputs/nist_config.json" `
  --kgr-metrics-output "outputs/kgr_metrics.csv" `
  --kgr-config-output "outputs/kgr_config.json" `
  --evaluation-xlsx-output "outputs/evaluation_summary.xlsx"
```

## 7. Current Git State & Verification
- **Active Branch**: `main`.
- **Working Tree Policy**: All modified and untracked files remain strictly unstaged in the working tree awaiting user review. No commits or pushes have been performed.
- **Gitignore Status**: Inspected `.gitignore`. The existing rule `outputs/*` (with `!outputs/.gitkeep`) already covers all generated artifacts, candidate keys, and visualizations. No `.gitignore` modification was required.

## 8. Remaining Limitations & Proposed Next Steps
- **Limitations & Scientific Notice**:
  - Operates on synthetic indoor dummy data for software verification; cannot establish empirical secrecy.
  - Channel probing hardware is deferred to a subsequent physical testing phase.
  - Parameters $W=50$ and $\alpha=0.5$ are provisional software-validation settings, not optimized physical-channel parameters.
  - PRBS bit expansion is deterministic and does not add physical channel entropy.
  - Helper data reveals parity relations and leaks information; SHA-256 output length (256 bits) does not establish 256 bits of min-entropy.
  - **Global BCH Secrecy Limitation**: While global $\text{BCH}(1023, 46, 200)$ successfully reconciles both paths to 100% KAR for Alice–Bob, without interleaving known padding reveals the final PRBS block ($N_{\text{pad}} = 546$ on Block 1); the reported full-stream attack additionally uses per-sample PRBS parity constraints to achieve joint $\text{GF}(2)$ full rank 92/92 across both blocks, allowing Eve to solve Alice's private message algebraically from helper data alone. Standard Eve decoder failure does not establish secrecy.
  - **Mandatory Disclaimer**: *Dummy-data comparison; shared configuration has reported public-information leakage. KAR does not establish secrecy.* This shared configuration mode is strictly for algorithmic benchmarking and comparative analysis; it is **NOT** claimed to be cryptographically secure.
  - **NIST Randomness & KGR Scope**:
    - The three NIST tests (Monobit, Runs, Approximate Entropy) validate basic statistical randomness properties of the 256-bit hash digests on dummy data. Passing these tests does NOT claim a full NIST SP 800-22 suite pass, physical entropy, or cryptographic unpredictability.
    - Repeated software timing runs do NOT constitute independent randomness samples. Duplicate matching keys from Bob are never concatenated or double-counted to inflate bit counts.
    - KGR measures pure software execution throughput ($N_{\text{accepted\_bits}} / T$) on a local machine with a pre-warmed JIT cache, NOT an empirical channel probing rate or over-the-air throughput.
- **Pipeline Roadmap**:
  1. *Completed*: Implemented Modified Sage–Husa Adaptive Kalman Filter (MSHKF) stage.
  2. *Completed*: Implemented Modified Adaptive Dual-Threshold Quantization (MADQ) stage (`PA.pdf` Section 3.2.3, Equations 3.21–3.23) and KAR evaluation (Equation 3.64).
  3. *Completed*: Implemented Bit Expansion with Galois XOR-LFSR PRBS generator (`PA.pdf` Section 3.2.4 as background) and before/after KAR evaluation.
  4. *Completed*: Implemented BCH Codeword-based Information Reconciliation (`PA.pdf` Section 3.2.5, Equations 3.32–3.36).
  5. *Completed*: Unified global BCH configuration architecture (`DEFAULT_BCH_CODE = (1023, 46, 200)` with derived $d=401$, Interleaving OFF), eliminated legacy mode branching, and rejected obsolete flags.
  6. *Completed*: Implemented bit-level SHA-256 Privacy Amplification (`PA.pdf` Section 3.2.6, Equations 3.37–3.53), yielding 256-bit secret keys across both reconciled 2-bit paths, verified 100% Alice-Bob match and ~50% Eve decorrelation (avalanche effect).
  7. *Completed*: Implemented NIST SP 800-22 statistical test suite (`monobit_test`, `runs_test`, `approximate_entropy_test`) per `PA.pdf` Section 3.2.8.d (Equations 3.65–3.73), verified against official NIST reference test vectors, explicit Runs prerequisite enforcement, and CSV/JSON exporters.
  8. *Completed*: Implemented Key Generation Rate (KGR) measurement per `PA.pdf` Section 3.2.8.b (Equation 3.63) with high-resolution monotonic timer, single Alice key accounting, BCH cache pre-warming, and companion multi-sheet Excel workbook export.
  9. *Proposal*: Implement physical channel probing with real wireless hardware and evaluate empirical entropy.
