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

- **Tahap Kuantisasi (Modified Adaptive Dual-Threshold Quantization / MADQ)**: Sesuai **Bagian 3.2.3, Persamaan (3.21)–(3.23), halaman 27–28**:
  - Segmentasi: Sinyal RSSI hasil penapisan dibagi menjadi segmen-segmen non-overlapping berukuran $W$ (default: $W = 50$, nilai sementara validasi perangkat lunak).
  - Statistik segmen: Untuk setiap segmen dan kanal dihitung rerata $\mu_X$ dan standar deviasi populasi $\sigma_X$ ($\text{ddof} = 0$).
  - Ambang batas atas dan bawah:
    $$q_i^+ = \mu_X + \alpha \sigma_X \qquad (3.21)$$
    $$q_i^- = \mu_X - \alpha \sigma_X \qquad (3.22)$$
    dengan koefisien pengali $\alpha = 0.5$ (nilai sementara validasi perangkat lunak).
  - Penentuan level kuantisasi:
    $$Q(X_i) = \begin{cases} 0, & X_i < q_i^- \\ 1, & q_i^- \le X_i \le q_i^+ \\ 2, & X_i > q_i^+ \end{cases} \qquad (3.23)$$
  - Retensi sampel: Seluruh sampel dipertahankan (tidak ada sampel di zona tengah yang dibuang). Segmen konstan ($\sigma_X = 0$) menghasilkan level 1.
  - Representasi biner:
    - **2-bit Gray code**: $0 \rightarrow 00$, $1 \rightarrow 01$, $2 \rightarrow 11$ (pilihan implementasi untuk meminimalkan bit error).
    - **4-bit code**: $0 \rightarrow 1010$, $1 \rightarrow 1011$, $2 \rightarrow 1001$ (sesuai `PA.pdf` Bagian 3.2.3, halaman 28).
  - Evaluasi Key Agreement Rate (KAR) sesuai **Bagian 3.2.8.c, Persamaan (3.64), halaman 35**:
    $$\text{KAR} = \left(1 - \frac{N_{\text{mismatch}}}{N_{\text{total}}}\right) \times 100\% = \frac{N_{\text{total}} - N_{\text{mismatch}}}{N_{\text{total}}} \times 100\%$$

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
   - *Row-wise sample alignment*: Setiap baris data mewakili indeks observasi waktu yang sama di keempat kolom. Urutan baris dan penjajaran dipertahankan secara utuh sebelum dan sesudah filtering dan kuantisasi.
   - *Channel Isolation*: Setiap kanal ditapis dan dikuantisasi secara mandiri dengan instance/threshold terpisah.
   - *Keluaran Validasi Korelasi*:
     - `Alice–Bob`: $\rho_{\text{raw}} = +0.632263 \rightarrow \rho_{\text{filt}} = +0.842244$ ($\Delta\rho = +0.209981$)
     - `Alice–Eve1-Alice`: $\rho_{\text{raw}} = +0.017060 \rightarrow \rho_{\text{filt}} = -0.013725$ ($\Delta\rho = -0.030784$)
     - `Bob–Eve1-Bob`: $\rho_{\text{raw}} = +0.119310 \rightarrow \rho_{\text{filt}} = +0.015151$ ($\Delta\rho = -0.104159$)
   - *Keluaran Validasi Kuantisasi ($N=500, W=50, \alpha=0.5$)*:
     - Jumlah segmen: 10 segmen.
     - Panjang bitstream: 1.000 bit (2-bit Gray), 2.000 bit (4-bit).
     - `Alice–Bob`: Level Agreement = 64,4000%, 2-bit Gray KAR = 80,4000%, 4-bit KAR = 90,2000%.
     - `Alice–Eve1-Alice`: Level Agreement = 34,8000%, 2-bit Gray KAR = 58,2000%, 4-bit KAR = 79,1000%.
     - `Bob–Eve1-Bob`: Level Agreement = 34,4000%, 2-bit Gray KAR = 55,4000%, 4-bit KAR = 77,7000%.
     - Efek encoding 4-bit: Prefiks '10' yang sama di ketiga simbol menjamin kecocokan struktural minimum 50% (KAR_4bit = 50% + KAR_2bit / 2) tanpa memandang korelasi level; pelaporan level agreement tetap penting untuk transparansi.
