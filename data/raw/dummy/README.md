# Dummy RSSI Data

Dataset dummy untuk keperluan validasi perangkat lunak (software validation pipeline).

## File
- `Dummy RSSI (data Indoor).xlsx`: 500 sampel pengukuran RSSI indoor sintetis/dummy.

## Kolom Data
- `Alice`: Nilai RSSI yang diterima oleh node Alice.
- `Bob`: Nilai RSSI yang diterima oleh node Bob.
- `Eve1-Alice`: Nilai RSSI yang disadap oleh Eve dari transmisi Alice.
- `Eve1-Bob`: Nilai RSSI yang disadap oleh Eve dari transmisi Bob.

## Catatan Penting
- Data ini ditujukan eksklusif untuk software verification, **bukan** untuk klaim empiris mengenai perilaku channel nirkabel riil.
- Konfirmasi penyejajaran sampel berbasis baris (*row-wise sample alignment*) antar kolom wajib dilakukan sebelum tahap implementasi kalkulasi korelasi Pearson.
