# RSSI-based Secret Key Generation (SKG) Research

Repositori ini menyediakan perancah (*scaffolding*) proyek Python minimal untuk penelitian Secret Key Generation (SKG) berbasis Received Signal Strength Indicator (RSSI).

> **Dokumen Handoff Progres**: Lihat [docs/progress.md](docs/progress.md) untuk ringkasan mandiri status proyek, hasil validasi korelasi, dan instruksi reproduksi.

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
│   └── rssi_skg/                     # Modul paket sumber utama Python (loader, correlation, plotting, cli)
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── correlation.py
│       ├── loader.py
│       └── plotting.py
├── tests/                            # Pengujian unit dan validasi software
│   ├── __init__.py
│   ├── test_correlation.py
│   ├── test_loader.py
│   └── test_plotting.py
├── .gitignore                        # Konfigurasi pengabaian file cache, venv, dan outputs
├── PA.pdf                            # Dokumen acuan metodologis utama
├── pyproject.toml                    # Metadata proyek Python minimal (PEP 517/621)
└── README.md                         # Dokumentasi utama proyek
```

### Rincian Tanggung Jawab
- `src/rssi_skg/`: Tempat kode pustaka Python untuk pipeline SKG (modul `loader`, `correlation`, `plotting`, dan `cli`).
- `tests/`: Tempat pengujian otomatis (*unit tests*) untuk memastikan kebenaran algoritma dan integritas transformasi data (`test_correlation.py`, `test_loader.py`, `test_plotting.py`).
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

---

## Implementasi Tahap Korelasi (Pearson Correlation Stage)

- **Referensi Metodologis**: Mengacu pada dokumen `PA.pdf`, **Persamaan (3.62), halaman 34**:
  $$\rho_{X, Y} = \frac{\sum_{i=1}^{n} (X_i - \bar{X})(Y_i - \bar{Y})}{\sqrt{\sum_{i=1}^{n} (X_i - \bar{X})^2} \sqrt{\sum_{i=1}^{n} (Y_i - \bar{Y})^2}}$$
- **Sifat Analisis**: Korelasi Pearson dihitung pada *zero lag* (bukan *lag-search cross-correlation*).
- **Pasangan Kanal yang Dihitung**:
  1. `Alice–Bob`: Estimasi resiprositas antara pasangan sah.
  2. `Alice–Eve1-Alice`: Korelasi antara transmisi Alice dan penyadapan oleh Eve.
  3. `Bob–Eve1-Bob`: Korelasi antara transmisi Bob dan penyadapan oleh Eve.
- **Integritas Sampel**:
  - Penyejajaran sampel baris-ke-baris (*row-wise sample alignment*) terkonfirmasi mewakili indeks observasi yang sama untuk seluruh kolom. Urutan baris dipertahankan secara utuh.
  - Validasi ketat menolak nilai *missing*, non-numerik, atau non-terhingga (*NaN/Inf*) dengan pelaporan nomor baris dan nama kolom secara spesifik.
  - Deret bernilai konstan (variansi nol) diperlakukan sebagai korelasi tak terdefinisi (*undefined*) dan menghasilkan pesan kesalahan eksplisit.
  - Jumlah observasi tidak dikunci pada 500 (mendukung sembarang $N \ge 2$).

---

## Petunjuk Penyiapan Lingkungan & Eksekusi

Petunjuk eksekusi dari *root repository* pada Windows PowerShell menggunakan eksekutor langsung `.\.venv\Scripts\python.exe` sehingga aktivasi manual bersifat opsional:

### 1. Inisialisasi Lingkungan Virtual Lokal (.venv)
Gunakan *virtual environment* lokal proyek (bukan instalasi paket global):

```powershell
# Membuat virtual environment lokal
python -m venv .venv

# (Opsional) Mengaktifkan virtual environment di PowerShell
.\.venv\Scripts\Activate.ps1

# Memasang proyek dan seluruh dependensi pengembangan dalam mode editable
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

### 2. Menjalankan Pengujian Unit (*Unit Tests*)
Pengujian mencakup korelasi sempurna (+1.0 dan -1.0), ortogonal/nol, deret konstan, panjang tidak sama, kolom hilang, nilai tidak valid, preservasi urutan baris, agregasi titik identik untuk scatter bubble, pembuatan gambar, serta perbandingan independen terhadap `scipy.stats.pearsonr`:

```powershell
# Menjalankan seluruh pengujian unit (19 tests)
.\.venv\Scripts\python.exe -m pytest -v

# Atau jika venv telah aktif:
pytest -v
```

### 3. Menjalankan Analisis Korelasi via CLI

#### A. Eksekusi CSV Saja (Tanpa Pembuatan Grafik)
Gunakan opsi `-i/--input` dan `-o/--output`:
```powershell
.\.venv\Scripts\python.exe -m rssi_skg -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" -o "outputs/dummy_rssi_correlation.csv"
```

#### B. Eksekusi Lengkap (Ekspor CSV dan Grafik PNG 300 dpi + PDF)
Sertakan opsi `--figure-prefix` untuk mengekspor gambar grafik gabungan:
```powershell
.\.venv\Scripts\python.exe -m rssi_skg -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" -o "outputs/dummy_rssi_correlation.csv" --figure-prefix "outputs/dummy_rssi_correlation"

# Atau menggunakan console entry point yang terdaftar (jika venv aktif):
rssi-skg -i "data/raw/dummy/Dummy RSSI (data Indoor).xlsx" -o "outputs/dummy_rssi_correlation.csv" --figure-prefix "outputs/dummy_rssi_correlation"
```

### 4. Lokasi File Keluaran (*Outputs*)
Semua artefak yang dihasilkan tersimpan di direktori `outputs/` (diabaikan oleh Git melalui `.gitignore`, kecuali `.gitkeep`):
- `outputs/dummy_rssi_correlation.csv`: Tabel koefisien korelasi Pearson dengan presisi penuh (`float64`) untuk ketiga pasangan kanal (`Alice–Bob`, `Alice–Eve1-Alice`, `Bob–Eve1-Bob`), jumlah sampel ($N=500$), dan kolom `data_kind`.
- `outputs/dummy_rssi_correlation.png`: Grafik gabungan visualisasi korelasi resolusi tinggi (300 dpi) yang memuat *horizontal bar chart* di bagian atas dan 3 panel *bubble scatter* di bawahnya.
- `outputs/dummy_rssi_correlation.pdf`: Grafik gabungan dalam format vektor PDF untuk dokumen/laporan penelitian.

---

## Batasan & Peringatan Metodologis

Hasil analisis ini adalah untuk **validasi perangkat lunak (software verification)** menggunakan data dummy sintetis. Hasil koefisien korelasi yang diperoleh **tidak boleh digunakan untuk menarik kesimpulan keamanan empiris atau karakteristik propagasi kanal fisik riil**, karena pengujian *channel probing* fisik masih berstatus ditunda (*postponed*).
