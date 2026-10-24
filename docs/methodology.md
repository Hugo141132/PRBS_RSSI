# Dokumentasi Metodologi: Filtering & Analisis Korelasi

## Referensi Metodologis
- Dokumen acuan utama: `PA.pdf`.
- **Tahap Penapisan (Filtering)**: Modified Sage–Husa Adaptive Kalman Filter (MSHKF) sesuai **Bagian 3.2.2, Persamaan (3.10)–(3.20), halaman 26–27**:
  - Model RSSI skalar: $\Phi = 1.0$ (asumsi kanal berubah lambat), $H = 1.0$ (observasi langsung RSSI dalam dBm).
  - Parameter adaptif: Forgetting factor $b = 0.99$ (nilai terpilih dalam rentang literatur $0.95 \le b \le 0.999$ pada `PA.pdf` Bagian 3.2.2, bukan nilai tunggal yang diwajibkan secara preskriptif), bobot awal $D_0 = 1.0$.
  - Parameter $P_0, Q, R_0$: Merupakan asumsi validasi perangkat lunak belum terkalibrasi (*uncalibrated software-validation assumptions*), bukan hasil pengukuran properti fisik transceiver atau kanal.
  - Mode adaptasi: Kovariansi process noise $Q$ dipertahankan tetap (*fixed* pada $0.1\ \text{dBm}^2$); kovariansi measurement noise $\hat{R}_k$ diestimasi adaptif online; rerata noise $\hat{q}_k$ dan $\hat{r}_k$ diperbarui rekursif.
  - Alasan tidak mengadaptasi $Q$ via Persamaan (3.20): Implementasi ini secara spesifik mengikuti asumsi akhir dalam `PA.pdf` Bagian 3.2.2 (halaman 27), di mana kovariansi *process noise* $Q$ diasumsikan bernilai konstan/diketahui (*known prior*), sehingga kovariansi *measurement noise* $\hat{R}_k$ diestimasi secara adaptif online dan pembaruan adaptif $Q$ pada Persamaan (3.20) tidak dijalankan.
  - Kebijakan indeks sampel: $x_0 = z_0$ menetapkan baseline awal tanpa bias transient dan tidak dimasukkan ke dalam pembaruan pengukuran inovasi, mencegah *double-counting*.
- **Tahap Korelasi**: Koefisien korelasi Pearson *zero lag* sesuai **Persamaan (3.62), halaman 34**:

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

Di mana:
- $X_u(n)$: Nilai sampel RSSI kanal $u$ pada indeks observasi $n$.
- $X_v(n)$: Nilai sampel RSSI kanal $v$ pada indeks observasi $n$.
- $\mu_u$: Rerata sampel RSSI kanal $u$ ($\mu_u = \frac{1}{N}\sum_{n=1}^N X_u(n)$).
- $\mu_v$: Rerata sampel RSSI kanal $v$ ($\mu_v = \frac{1}{N}\sum_{n=1}^N X_v(n)$).
- $N$: Jumlah total pasangan observasi ($N = 500$ pada dataset dummy validasi).
*(Catatan: Notasi $u, v$ ini ekuivalen secara matematis dengan notasi $X, Y$ sebelumnya).*

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
3. **Konfirmasi & Status Implementasi**:
   - *Row-wise sample alignment*: Setiap baris data mewakili indeks observasi waktu yang sama di keempat kolom. Urutan baris dan penjajaran dipertahankan secara utuh sebelum dan sesudah filtering.
   - *Channel Isolation*: Setiap kanal ditapis secara mandiri dengan instance filter terpisah.
   - *Keluaran Validasi*:
     - `Alice–Bob`: $\rho_{\text{raw}} = +0.632263 \rightarrow \rho_{\text{filt}} = +0.842244$ ($\Delta\rho = +0.209981$)
     - `Alice–Eve1-Alice`: $\rho_{\text{raw}} = +0.017060 \rightarrow \rho_{\text{filt}} = -0.013725$ ($\Delta\rho = -0.030784$)
     - `Bob–Eve1-Bob`: $\rho_{\text{raw}} = +0.119310 \rightarrow \rho_{\text{filt}} = +0.015151$ ($\Delta\rho = -0.104159$)
