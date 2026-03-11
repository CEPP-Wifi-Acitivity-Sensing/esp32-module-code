# csi_recv
This code is used for a ESP32s3 board

## Uploading Code onto the board
- Locate ESP-IDF extension on VScode
- Select csi_recv workspace
- Select ESP-IDF version
- Select Flash Method : `UART`
- Select Port and Monitor Port
    - If undetected
         - Port is fucked
         - The current USB-C cable doesn't support data transfer
- Set Espressif Device Target (IDF Target) : `ESP32` > `ESP32 chip (via ESP-PROG)`
- Build and Flash

## Exporting Data
- Run
`python .\csi_data_read_parse.py -p <PORT> -s <PATH>/<FILE_NAME>.csv`

## Converting to .mat
- `cd convert_to_mat`
- `python to_mat.py <CSV_PATH> <OUTPUT_NAME>`