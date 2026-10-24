# RSSI-based Secret Key Generation (SKG) Research

Repositori ini menyediakan perancah (*scaffolding*) proyek Python untuk penelitian Secret Key Generation (SKG) berbasis Received Signal Strength Indicator (RSSI).

> **Dokumen Handoff Progres**: Lihat [docs/progress.md](docs/progress.md) untuk ringkasan mandiri status proyek, hasil validasi filtering dan korelasi, serta instruksi reproduksi.

---

## Struktur Direktori & Tanggung Jawab Folder

```text
PRBS_RSSI/
├── data/
│   └── raw/
│       ├── dummy/                    # Dataset dummy untuk validasi perangkat lunak
│       │   ├── Dummy RSSI (data Indoor).xlsx
│       │   └── README.md
│       └── measured/                 # Dicadangkan untuk data pengukuran channel probing fisik empiris
│           └── README.md
├── docs/                             # Catatan metodologis, referensi persamaan, dan dokumen handoff
│   ├── methodology.md
│   └── progress.md
├── outputs/                          # Artefak kalkulasi, plot, dan hasil eksekusi (diabaikan oleh Git via .gitignore)
│   └── .gitkeep
├── src/
│   └── rssi_skg/                     # Modul paket sumber utama Python (loader, filter, correlation, plotting, cli)
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── correlation.py
│       ├── filter.py
│       ├── loader.py
│       └── plotting.py
├── tests/                            # Pengujian unit dan validasi software
│   ├── __init__.py
│   ├── test_correlation.py
│   ├── test_filter.py
│   ├── test_loader.py
│   └── test_plotting.py
├── .gitignore                        # Konfigurasi pengabaian file cache, venv, dan outputs
├── PA.pdf                            # Dokumen acuan metodologis utama
├── pyproject.toml                    # Metadata proyek Python minimal (PEP 517/621)
└── README.md                         # Dokumentasi utama proyek
```

### Rincian Tanggung Jawab
- `src/rssi_skg/`: Tempat kode pustaka Python untuk pipeline SKG:
  - `loader.py`: Pemuatan workbook Excel dan validasi integritas baris/kolom.
  - `filter.py`: Implementasi Modified Sage–Husa Adaptive Kalman Filter (MSHKF) skalar (`PA.pdf` Bagian 3.2.2).
  - `correlation.py`: Komputasi koefisien korelasi Pearson *zero lag* (`PA.pdf` Persamaan 3.62).
  - `plotting.py`: Visualisasi bubble scatter agregat dan grafik komparasi sebelum/sesudah penapisan.
  - `cli.py`: Antarmuka CLI terpadu yang mendukung mode korelasi murni (default) dan mode filtering opsional.
- `tests/`: Tempat pengujian otomatis (*unit tests*) untuk memastikan kebenaran algoritma, isolasi kanal, safeguards numerik, dan pengujian regresi (`test_correlation.py`, `test_filter.py`, `test_loader.py`, `test_plotting.py`).
- `data/raw/dummy/`: Tempat dataset dummy untuk keperluan validasi software. Berisi `Dummy RSSI (data Indoor).xlsx` dan dokumentasi lokal `README.md`.
- `data/raw/measured/`: Folder cadangan khusus untuk data hasil pengukuran channel nirkabel riil (channel probing fisik empiris).
- `outputs/`: Menyimpan output kalkulasi, visualisasi, dan laporan. Dikecualikan dari pelacakan Git kecuali `.gitkeep`.
- `docs/`: Dokumentasi teknis, rujukan persamaan matematika dari literatur, log keputusan riset (`methodology.md`), dan ringkasan *handoff* ([docs/progress.md](docs/progress.md)).

---

## Provenance & Definisi Data Dummy

- **Sumber File**: `Dummy RSSI (data Indoor).xlsx` (500 baris sampel).
- **Semantik Kolom**:
  - `Alice`: Nilai RSSI yang diterima oleh Alice dari transmisi Bob.
  - `Bob`: Nilai RSSI yang diterima oleh Bob dari transmisi Alice.
  - `Eve1-Alice`: Nilai RSSI yang disadap dan diterima oleh pihak ketiga (Eve) dari sinyal transmisi Alice.
  - `Eve1-Bob`: Nilai RSSI yang disadap dan diterima oleh pihak ketiga (Eve) dari sinyal transmisi Bob.
- **Batasan & Fungsi**:
  Data dummy ini digunakan khusus untuk **software validation** (memvalidasi alur fungsi, parsing data, dan ketepatan komputasi program), **bukan** untuk membuat klaim empiris atau kesimpulan teoritis mengenai karakteristik kanal propagasi nirkabel yang sebenarnya.
- **Status Channel Probing**:
  Pengukuran kanal fisik secara empiris saat ini berstatus **ditunda (*postponed*)**, bukan digantikan (*not replaced*). Pengujian kanal nyata akan dilakukan pada tahap pengujian perangkat keras selanjutnya.

---

## Implementasi Tahap Filtering (Modified Sage–Husa AKF)

- **Referensi Metodologis**: Mengacu pada dokumen `PA.pdf`, **Bagian 3.2.2, Persamaan (3.10)–(3.20), halaman 26–27**:
  - **Asumsi Pemodelan RSSI Skalar**:
    - Matriks transisi status $\Phi = 1.0$ (model kanal RSSI statis/berubah lambat: $X_k = X_{k-1} + q_{k-1} + w_{k-1}$).
    - Matriks pengukuran $H = 1.0$ (observasi langsung RSSI skalar dalam dBm: $Z_k = X_k + r_k + v_k$).
  - **Mode Adaptasi Noise**:
    - Nilai kovariansi *process noise* $Q$ dijaga **tetap (*fixed*)** sebesar $0.1\ \text{dBm}^2$.
    - Nilai kovariansi *measurement noise* $\hat{R}_k$ diadaptasi secara online via Persamaan (3.15).
    - Rerata derau proses $\hat{q}_k$ dan derau pengukuran $\hat{r}_k$ diperbarui secara rekursif via Persamaan (3.19) dan (3.13).
  - **Rasionalisasi Peniadaan Update Adaptif $Q$ (Persamaan 3.20)**:
    Implementasi ini secara spesifik mengikuti asumsi pemodelan pada paragraf akhir `PA.pdf` Bagian 3.2.2 (halaman 27), di mana nilai kovariansi *process noise* $Q$ diasumsikan bernilai konstan dan telah diketahui nilainya (*known prior*), sehingga kovariansi *measurement noise* $\hat{R}_k$ diestimasi secara adaptif online dan pembaruan adaptif $Q$ pada Persamaan (3.20) tidak dijalankan.
  - **Urutan Perhitungan yang Dipelihara**:
    1. **Bobot adaptif** (Persamaan 3.10):
       ```math
       D_k = \frac{D_{k-1}}{D_{k-1} + b}, \quad D_0 = 1
       ```
    2. **Prediksi status** (Persamaan 3.11):
       ```math
       \hat{X}(k|k-1) = \Phi \hat{X}_{k-1} + \hat{q}_{k-1}
       ```
    3. **Prediksi kovariansi error** (Persamaan 3.12):
       ```math
       P(k|k-1) = \Phi P_{k-1} \Phi^T + Q
       ```
    4. **Pembaruan rerata measurement noise** (Persamaan 3.13):
       ```math
       \hat{r}_k = (1 - D_k)\hat{r}_{k-1} + D_k \left(Z_k - H \hat{X}(k|k-1)\right)
       ```
    5. **Perhitungan inovasi (menggunakan $\hat{r}_k$ yang baru)** (Persamaan 3.14):
       ```math
       e_k = Z_k - H \hat{X}(k|k-1) - \hat{r}_k
       ```
    6. **Pembaruan kovariansi measurement noise** (Persamaan 3.15):
       ```math
       \hat{R}_k = (1 - D_k)\hat{R}_{k-1} + D_k e_k^2
       ```
    7. **Penguatan Kalman** (Persamaan 3.16):
       ```math
       K_k = \frac{P(k|k-1) H^T}{H P(k|k-1) H^T + \hat{R}_k}
       ```
    8. **Pembaruan status** (Persamaan 3.17):
       ```math
       \hat{X}_k = \hat{X}(k|k-1) + K_k e_k
       ```
    9. **Pembaruan kovariansi error** (Persamaan 3.18):
       ```math
       P_k = (1 - K_k H) P(k|k-1)
       ```
    10. **Pembaruan rerata process noise** (Persamaan 3.19):
        ```math
        \hat{q}_k = (1 - D_k)\hat{q}_{k-1} + D_k \left(\hat{X}_k - \Phi \hat{X}_{k-1}\right)
        ```

### Parameter Konfigurasi, Satuan & Rasionalisasi

| Parameter | Nilai Default | Satuan | Status Spesifikasi | Rasionalisasi |
| :--- | :--- | :--- | :--- | :--- |
| $b$ | `0.99` | Tak berdimensi | Nilai Terpilih dalam Rentang Literatur | Nilai terpilih dalam rentang literatur yang dinyatakan pada `PA.pdf` Bag. 3.2.2 ($0.95 \le b \le 0.999$), bukan nilai tunggal yang diwajibkan secara preskriptif. Memberikan horizon memori efektif $\approx 100$ sampel. |
| $D_0$ | `1.0` | Tak berdimensi | Eksplisit (`PA.pdf` Pers. 3.10) | Bobot adaptif awal pada langkah $k=0$. |
| $\Phi$ | `1.0` | Tak berdimensi | Asumsi Pemodelan | Asumsi transisi keadaan kanal nirkabel berubah lambat. |
| $H$ | `1.0` | Tak berdimensi | Asumsi Pemodelan | Matriks observasi langsung sinyal RSSI skalar. |
| $x_0$ | Auto (`z[0]`) | $\text{dBm}$ | Asumsi Implementasi | Menginisialisasi keadaan awal dari sampel pertama kanal agar tidak ada bias *transient*. |
| $P_0$ | `1.0` | $\text{dBm}^2$ | Asumsi Validasi Perangkat Lunak | Kovariansi error awal belum terkalibrasi (*uncalibrated software-validation assumption*), bukan properti fisik transceiver/kanal terukur. |
| $q_0$ | `0.0` | $\text{dBm}$ | Asumsi Implementasi | Rerata awal *process noise* (asumsi tanpa *drift* sistematis awal). |
| $r_0$ | `0.0` | $\text{dBm}$ | Asumsi Implementasi | Rerata awal *measurement noise* (asumsi tanpa bias awal). |
| $Q$ | `0.1` | $\text{dBm}^2$ | Asumsi Validasi Perangkat Lunak | Kovariansi *process noise* konstan belum terkalibrasi (*uncalibrated software-validation assumption*), bukan properti fisik transceiver/kanal terukur. Sesuai asumsi `PA.pdf` Bag. 3.2.2, nilai $Q$ diasumsikan diketahui (*known prior*). |
| $R_0$ | `1.0` | $\text{dBm}^2$ | Asumsi Validasi Perangkat Lunak | Kovariansi *measurement noise* awal belum terkalibrasi (*uncalibrated software-validation assumption*), bukan properti fisik transceiver/kanal terukur. |

### Kebijakan Pengindeksan Sampel (*Sample Indexing*)
Untuk mencegah penghitungan ganda (*double-counting*) pada observasi pertama:
- Ketika $x_0$ diinisialisasi otomatis dari observasi pertama ($x_0 = z_0$), sampel $z_0$ ditetapkan sebagai status pada indeks waktu 0 ($\hat{X}_0 = z_0$). Loop pembaruan rekursif Persamaan (3.10)–(3.19) dimulai dari pengukuran $z_1$ pada langkah $k=1$. Dengan demikian, $z_0$ digunakan tepat satu kali sebagai keadaan awal dan **tidak pernah dihitung ulang sebagai input inovasi pengukuran**.
- Jika prior $x_0$ diberikan secara eksplisit dari luar, maka seluruh pengukuran $z_0, \dots, z_{N-1}$ diproses pada langkah $k = 1, \dots, N$.

### Isolasi Kanal & Pengamanan Numerik (*Numerical Safeguards*)
- **Isolasi Kanal**: Saluran Alice, Bob, Eve1-Alice, dan Eve1-Bob diproses menggunakan *instance filter* terpisah secara independen. Tidak ada *state* yang dibagi antarkanal.
- **Validasi Nilai Terhingga**: Memeriksa `math.isfinite` pada seluruh sampel input; menolak nilai `NaN`, `+Inf`, dan `-Inf` secara eksplisit.
- **Safeguard Kovariansi**: Memastikan $\hat{R}_k \ge R_{\min} = 10^{-8}\ \text{dBm}^2$, $P_k \ge 0.0$, memvalidasi penyebut penguatan Kalman tidak singular ($P_{\text{pred}} + \hat{R}_k > 0$), serta membangkitkan `FloatingPointError` jika terjadi kovariansi negatif signifikan atau hasil non-terhingga (tidak disembunyikan secara diam-diam).

---

## Implementasi Tahap Korelasi (Pearson Correlation Stage)

- **Referensi Metodologis**: Mengacu pada dokumen `PA.pdf`, **Persamaan (3.62), halaman 34**:
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
  Di mana:
  - $X_u(n)$: Nilai sampel RSSI pada kanal $u$ pada indeks observasi $n$.
  - $X_v(n)$: Nilai sampel RSSI pada kanal $v$ pada indeks observasi $n$.
  - $\mu_u$: Rerata sampel RSSI kanal $u$ sepanjang $N$ observasi ($\mu_u = \frac{1}{N}\sum_{n=1}^N X_u(n)$).
  - $\mu_v$: Rerata sampel RSSI kanal $v$ sepanjang $N$ observasi ($\mu_v = \frac{1}{N}\sum_{n=1}^N X_v(n)$).
  - $N$: Jumlah total pasangan observasi ($N = 500$ pada dataset dummy validasi).
  *(Catatan: Notasi $u, v$ ini secara matematis ekuivalen dengan notasi $X, Y$ sebelumnya).*
- **Sifat Analisis**: Korelasi Pearson dihitung pada *zero lag*.
- **Pasangan Kanal yang Dihitung**:
  1. `Alice–Bob`: Estimasi resiprositas antara pasangan sah ($u = \text{Alice}, v = \text{Bob}$).
  2. `Alice–Eve1-Alice`: Korelasi antara transmisi Alice dan penyadapan oleh Eve ($u = \text{Alice}, v = \text{Eve1-Alice}$).
  3. `Bob–Eve1-Bob`: Korelasi antara transmisi Bob dan penyadapan oleh Eve ($u = \text{Bob}, v = \text{Eve1-Bob}$).

### Hasil Korelasi Sebelum vs Sesudah Filtering ($N=500$, `data_kind=dummy`)

| Pasangan Kanal | Korelasi Raw ($\rho_{\text{raw}}$) | Korelasi Filtered ($\rho_{\text{filt}}$) | Perubahan ($\Delta\rho$) |
| :--- | :--- | :--- | :--- |
| `Alice–Bob` | `+0.632263` | `+0.842244` | `+0.209981` |
| `Alice–Eve1-Alice` | `+0.017060` | `-0.013725` | `-0.030784` |
| `Bob–Eve1-Bob` | `+0.119310` | `+0.015151` | `-0.104159` |

*(Catatan: Penapisan MSHKF meningkatkan korelasi resiprokal pasangan sah Alice–Bob sekaligus menekan korelasi kanal penyadap Eve mendekati nol pada dataset dummy validasi software).*

---

## Petunjuk Penyiapan Lingkungan & Eksekusi

Petunjuk eksekusi dari *root repository* pada Windows PowerShell menggunakan eksekutor langsung `.\.venv\Scripts\python.exe`:

### 1. Inisialisasi Lingkungan Virtual Lokal (.venv)
```powershell
# Membuat virtual environment lokal
python -m venv .venv

# (Opsional) Mengaktifkan virtual environment di PowerShell
.\.venv\Scripts\Activate.ps1

# Memasang proyek dan seluruh dependensi pengembangan dalam mode editable
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 2. Menjalankan Pengujian Unit (*Unit Tests*)
Pengujian mencakup 31 tes otomatis (validasi intermediate step-by-step perhitungan independen MSHKF, isolasi kanal, pengindeksan sampel, safeguards numerik, korelasi Pearson, loader workbook, dan pembuatan visualisasi):

```powershell
# Menjalankan seluruh pengujian unit (31 tests)
.\.venv\Scripts\python.exe -m pytest -v
```

### 3. Menjalankan Analisis via CLI

#### A. Eksekusi Korelasi Default (Tanpa Filtering - 100% Backward Compatible)
```powershell
.\.venv\Scripts\python.exe -m rssi_skg -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" -o "outputs/dummy_rssi_correlation.csv" --figure-prefix "outputs/dummy_rssi_correlation"
```

#### B. Eksekusi Lengkap dengan Tahap Filtering MSHKF
Jalankan CLI dengan menyertakan argumen `--filter` beserta pengeksporan artefak terpadu:
```powershell
.\.venv\Scripts\python.exe -m rssi_skg `
  -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" `
  -o "outputs/dummy_rssi_filtered_correlation.csv" `
  --filter `
  --filtered-samples-output "outputs/dummy_rssi_filtered_samples.csv" `
  --filter-config-output "outputs/dummy_rssi_filter_config.json" `
  --figure-prefix "outputs/dummy_rssi_filtered"
```

### 4. Lokasi File Keluaran (*Outputs*)
Semua artefak yang dihasilkan tersimpan di direktori `outputs/` (diabaikan oleh Git melalui `.gitignore`, kecuali `.gitkeep`):
- `outputs/dummy_rssi_correlation.csv`: Tabel koefisien korelasi raw untuk ketiga pasangan kanal ($N=500$).
- `outputs/dummy_rssi_correlation.png` / `.pdf`: Grafik visualisasi korelasi raw (horizontal bar + bubble scatter).
- `outputs/dummy_rssi_filtered_correlation.csv`: Tabel perbandingan koefisien korelasi raw vs filtered beserta nilai $\Delta\rho$.
- `outputs/dummy_rssi_filtered_samples.csv`: Deret sampel observasi mentah dan hasil filter yang disejajarkan per baris untuk 4 kanal.
- `outputs/dummy_rssi_filter_config.json`: Metadata konfigurasi lengkap MSHKF, asumsi pemodelan, satuan, dan rasionalisasinya.
- `outputs/dummy_rssi_filtered.png`: Visualisasi komparasi resolusi tinggi (300 dpi) yang memuat perbandingan bar horizontal, trayektori penghalusan waktu (*time series smoothing*), dan 3 panel scatter bubble terfilter.
- `outputs/dummy_rssi_filtered.pdf`: Visualisasi komparasi dalam format vektor PDF.

---

## Batasan & Peringatan Metodologis

Hasil analisis ini adalah untuk **validasi perangkat lunak (software verification)** menggunakan data dummy sintetis. Hasil koefisien korelasi yang diperoleh **tidak boleh digunakan untuk menarik kesimpulan keamanan empiris atau karakteristik propagasi kanal fisik riil**, karena pengujian *channel probing* fisik masih berstatus ditunda (*postponed*).
