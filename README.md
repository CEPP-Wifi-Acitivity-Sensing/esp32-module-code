# esp32-module-code
Stolen from [https://github.com/espressif/esp-csi](https://github.com/espressif/esp-csi) because I have no idea how to use github, please check out the original creator

## Why would I make this?
### Who am I?
I am working for a chinese government agency and I need to spy on people.
### Problem
- The [Wipose Dataset](https://github.com/NjtechCVLab/Wi-PoseDataset)'s dataset format is 5 CSI Data × 30 Subcarrier × 3 Transmitting Antennas × 3 Receiving Antennas, which was captured on a different hardware. 
- ESP32 captures CSI data in a different format, which is 1 CSI Data × 30 Subcarrier × 1 Transmitting Antenna × 1 Receiving Antenna.
- we're cooked.

### Solution
- Choice 1: Expanding the Data
    1. use 5 CSI data within a specific time window to simulate the 5 CSI data in the Wipose dataset format.
    2. expand the 1×1 CSI data to 3×3 CSI data by copying the same data to the other antennas, which is not ideal but hey it might works
- Choice 2: Five hundred million ESP32s3 boards
    1. use 5 different ESP32s3 boards to capture the CSI data simultaneously, immediately achieving 5×30×1×1
    2. expand the data 

Which one is better? idk bruh but I'm using the first one

## Setup
- Install ESP-IDF on VSCode via [EspressIf Official Website](https://docs.espressif.com/projects/esp-idf/en/stable/esp32/get-started/index.html)
- Five hundred ESP32s3 boards
- profit

## Get Started
1. Flash 1 ESP32 board with the sender code in `csi_send`
2. Flash the remaining 2 million ESP32s3 boards with the receiver code in `csi_recv`
3. Rent a $500,000/mo 30 square meters NYC apartment to set up the boards
4. Place the sender on the wall and the receivers on the other side facing each other, 6 meters apart
5. Connect the sender to a power source and the receivers to a PC