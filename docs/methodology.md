# Dokumentasi Metodologi & Rencana Analisis Korelasi

## Referensi Metodologis
- Dokumen acuan utama: `PA.pdf`.
- Tahap analisis korelasi mendatang menggunakan rumus koefisien korelasi Pearson sesuai **Persamaan (3.62), halaman 34**:
  $$\rho_{X, Y} = \frac{\sum_{i=1}^{n} (X_i - \bar{X})(Y_i - \bar{Y})}{\sqrt{\sum_{i=1}^{n} (X_i - \bar{X})^2} \sqrt{\sum_{i=1}^{n} (Y_i - \bar{Y})^2}}$$

## Sumber & Karakteristik Data
1. **Dummy Data**:
   - Sumber: `data/raw/dummy/Dummy RSSI (data Indoor).xlsx` (500 sampel).
   - Kolom:
     - `Alice`: RSSI received by Alice.
     - `Bob`: RSSI received by Bob.
     - `Eve1-Alice`: RSSI received by Eve from Alice.
     - `Eve1-Bob`: RSSI received by Eve from Bob.
   - Status & Peran: Digunakan hanya untuk verifikasi logika kode dan pipeline pengolahan (software validation), bukan untuk generalisasi perilaku propagasi kanal riil.
2. **Channel Probing**:
   - Status: Ditunda (*postponed*), bukan ditiadakan/digantikan. Pengukuran empiris akan menggunakan folder `data/raw/measured/`.
3. **Item Konfirmasi Sebelum Implementasi**:
   - *Row-wise sample alignment*: Perlu konfirmasi apakah indeks baris pada dummy dataset mencerminkan probe berurutan yang saling sinkron antar kanal (Alice-Bob vs Eve-Alice/Bob).
