# RSSI-based Secret Key Generation (SKG) Research

Repositori ini menyediakan perancah (*scaffolding*) proyek Python minimal untuk penelitian Secret Key Generation (SKG) berbasis Received Signal Strength Indicator (RSSI).

---

## Struktur Direktori & Tanggung Jawab Folder

```text
PRBS_RSSI/
├── data/
│   ├── dummy/
│   │   └── 00_input/                 # Dataset dummy original (dipertahankan tanpa perubahan)
│   └── raw/
│       ├── dummy/                    # Salinan kerja dataset dummy untuk validasi perangkat lunak
│       └── measured/                 # Dicadangkan untuk data pengukuran channel probing fisik empiris
├── docs/                             # Catatan metodologis, referensi persamaan, dan arsitektur riset
├── outputs/                          # Artefak kalkulasi, plot, dan hasil eksekusi (diabaikan oleh Git via .gitignore)
├── src/
│   └── rssi_skg/                     # Modul paket sumber utama Python (placeholder scaffolding)
├── tests/                            # Pengujian unit dan validasi software
├── .gitignore                        # Konfigurasi pengabaian file cache, venv, dan outputs
├── PA.pdf                            # Dokumen acuan metodologis utama
├── pyproject.toml                    # Metadata proyek Python minimal (PEP 517/621)
└── README.md                         # Dokumentasi utama proyek
```

### Rincian Tanggung Jawab
- `src/rssi_skg/`: Tempat kode pustaka Python untuk pipeline SKG (misalnya pembersihan data, kalkulasi korelasi, kuantisasi, dsb.). Saat ini hanya memuat `__init__.py`.
- `tests/`: Tempat pengujian otomatis (*unit tests*) untuk memastikan kebenaran algoritma dan integritas transformasi data.
- `data/raw/dummy/`: Tempat salinan data dummy untuk keperluan validasi software. Berisi `Dummy RSSI (data Indoor).xlsx`.
- `data/raw/measured/`: Folder cadangan khusus untuk data hasil pengukuran channel nirkabel riil (channel probing fisik).
- `data/dummy/00_input/`: Menyimpan file asli dari data dummy indoor yang tetap dipertahankan secara utuh (*unchanged*).
- `outputs/`: Menyimpan output kalkulasi, visualisasi, dan laporan. Dikecualikan dari pelacakan Git kecuali `.gitkeep`.
- `docs/`: Dokumentasi teknis, rujukan persamaan matematika dari literatur, dan log keputusan riset.

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

## Rencana Tahap Korelasi (Planned Correlation Stage)

- **Referensi Metodologis**: Mengacu pada dokumen `PA.pdf`.
- **Formulasi**: Implementasi kalkulasi berikutnya akan menerapkan koefisien korelasi Pearson berdasarkan **Persamaan (3.62), halaman 34**:
  $$\rho_{X, Y} = \frac{\sum_{i=1}^{n} (X_i - \bar{X})(Y_i - \bar{Y})}{\sqrt{\sum_{i=1}^{n} (X_i - \bar{X})^2} \sqrt{\sum_{i=1}^{n} (Y_i - \bar{Y})^2}}$$
- **Catatan & Syarat Validasi**:
  Sebelum kalkulasi korelasi diimplementasikan, **konfirmasi penyejajaran sampel baris-ke-baris (*row-wise sample alignment*)** wajib diverifikasi terlebih dahulu untuk memastikan sinkronisasi waktu/urutan probe antara pasangan sah (Alice-Bob) dan penyerang (Eve).

---

## Ruang Lingkup Saat Ini

Proyek ini berada pada tahap **scaffolding awal**:
- Tidak ada instalasi dependensi runtime pada sistem.
- Tidak memuat implementasi algoritma korelasi, dashboard, basis data, komunikasi MQTT, atau modul pipeline tingkat lanjut.
